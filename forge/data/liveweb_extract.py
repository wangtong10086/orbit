"""Extract LIVEWEB evaluation data from DynamoDB.

Queries the affine_sample_results table for liveweb environment entries,
decompresses conversation data, filters by score and length, and outputs
canonical JSONL format for training.

Reusable module — can be imported or used via CLI.
"""

import gzip
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# DDB schema constants (mirrors affine-cortex/affine/database/)
ENV_KEY = "affine:liveweb"
GSI_NAME = "timestamp-index"
GSI_PARTITION_VALUE = "SAMPLE"

# Sites we care about for coverage tracking
TRACKED_SITES = {
    "taostats.io": "taostats",
    "stooq.com": "stooq",
    "wttr.in": "weather",
    "coingecko.com": "coingecko",
}

# URL pattern to detect which site a page belongs to
_URL_PATTERN = re.compile(r"https?://(?:www\.)?([^/]+)")


@dataclass
class ExtractionConfig:
    """Configuration for liveweb DDB extraction."""
    aws_region: str = "us-east-1"
    table_prefix: str = "affine"
    min_score: float = 0.5
    max_chars: int = 32000  # ~8192 tokens at ~3.9 chars/token
    output_path: str = "data/liveweb_ddb.jsonl"

    @property
    def table_name(self) -> str:
        return f"{self.table_prefix}_sample_results"


@dataclass
class ExtractionResult:
    """Summary of extraction run."""
    total_scanned: int = 0
    score_filtered: int = 0
    length_filtered: int = 0
    decompress_errors: int = 0
    no_conversation: int = 0
    kept: int = 0
    site_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    score_distribution: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def _get_ddb_client(region: str):
    """Create a boto3 DynamoDB client.

    Uses IAM instance credentials (no access key needed on EC2/ECS).
    """
    try:
        import boto3
    except ImportError:
        raise ImportError(
            "boto3 is required for DDB access. Install with: pip install boto3"
        )
    return boto3.client("dynamodb", region_name=region)


def _deserialize_value(val: Dict) -> Any:
    """Convert a single DynamoDB typed value to Python."""
    if "NULL" in val:
        return None
    if "BOOL" in val:
        return val["BOOL"]
    if "N" in val:
        s = val["N"]
        return int(s) if "." not in s else float(s)
    if "S" in val:
        return val["S"]
    if "B" in val:
        return val["B"]
    if "L" in val:
        return [_deserialize_value(v) for v in val["L"]]
    if "M" in val:
        return {k: _deserialize_value(v) for k, v in val["M"].items()}
    return None


def _deserialize_ddb(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DynamoDB wire format to Python types."""
    return {k: _deserialize_value(v) for k, v in item.items()}


def decompress_extra(raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Decompress gzip-compressed extra field from DDB.

    Returns parsed dict or None on failure.
    """
    try:
        text = gzip.decompress(raw_bytes).decode("utf-8")
        return json.loads(text)
    except Exception:
        return None


def detect_sites(conversation: List[Dict]) -> List[str]:
    """Scan conversation messages for known site URLs.

    Returns list of detected site keys (e.g. ['taostats', 'coingecko']).
    """
    found = set()
    for msg in conversation:
        content = msg.get("content") or ""
        if not isinstance(content, str):
            continue
        for match in _URL_PATTERN.finditer(content):
            domain = match.group(1).lower()
            for site_domain, site_key in TRACKED_SITES.items():
                if site_domain in domain:
                    found.add(site_key)
    return sorted(found)


def normalize_messages(conversation: List[Dict]) -> List[Dict]:
    """Normalize messages to canonical (role, content) format.

    Strips tool_calls, tool_call_id, tools, name, and any other extra keys.
    Flattens tool_calls into assistant content where needed.
    """
    normalized = []
    for msg in conversation:
        role = msg.get("role", "")
        content = msg.get("content")

        if not role:
            continue

        # For assistant messages with tool_calls but empty/None content,
        # serialize the tool call as text content so information is preserved
        if role == "assistant" and not content and "tool_calls" in msg:
            tool_calls = msg["tool_calls"]
            if isinstance(tool_calls, list) and tool_calls:
                parts = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "unknown")
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.dumps(json.loads(args))
                        except (json.JSONDecodeError, TypeError):
                            pass
                    parts.append(json.dumps({"name": name, "arguments": args}))
                content = "\n".join(parts)

        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content)

        normalized.append({"role": role, "content": content})
    return normalized


def total_chars(messages: List[Dict]) -> int:
    """Count total characters across all message contents."""
    return sum(len(m.get("content", "")) for m in messages)


def extract_liveweb_from_ddb(
    config: ExtractionConfig,
    progress_callback=None,
) -> Tuple[List[Dict], ExtractionResult]:
    """Query DDB for liveweb samples, filter, and return canonical records.

    Uses the timestamp-index GSI to scan ALL samples, filtering server-side
    by env=affine:liveweb. The GSI has a fixed partition key 'SAMPLE' with
    timestamp as sort key, so we can query it efficiently.

    Args:
        config: Extraction configuration
        progress_callback: Optional callable(scanned, kept) for progress updates

    Returns:
        (records, result) — list of canonical dicts + extraction summary
    """
    result = ExtractionResult()
    client = _get_ddb_client(config.aws_region)
    records = []
    last_key = None

    while True:
        params = {
            "TableName": config.table_name,
            "IndexName": GSI_NAME,
            "KeyConditionExpression": "gsi_partition = :gp",
            "FilterExpression": "env = :env",
            "ExpressionAttributeValues": {
                ":gp": {"S": GSI_PARTITION_VALUE},
                ":env": {"S": ENV_KEY},
            },
            "ScanIndexForward": False,  # newest first
        }
        if last_key:
            params["ExclusiveStartKey"] = last_key

        response = client.query(**params)
        items = response.get("Items", [])

        for raw_item in items:
            result.total_scanned += 1
            item = _deserialize_ddb(raw_item)

            score = item.get("score", 0)
            if isinstance(score, (int, float)):
                score = float(score)
            else:
                continue

            # Score bucket for stats
            bucket = f"{int(score * 10) / 10:.1f}"
            result.score_distribution[bucket] += 1

            # Score filter
            if score < config.min_score:
                result.score_filtered += 1
                continue

            # Decompress extra
            extra_compressed = item.get("extra_compressed")
            if not extra_compressed:
                result.no_conversation += 1
                continue

            extra = decompress_extra(extra_compressed)
            if extra is None:
                result.decompress_errors += 1
                continue

            conversation = extra.get("conversation")
            if not conversation or not isinstance(conversation, list):
                result.no_conversation += 1
                continue

            # Normalize messages
            messages = normalize_messages(conversation)

            # Length filter
            chars = total_chars(messages)
            if chars > config.max_chars:
                result.length_filtered += 1
                continue

            # Detect sites visited
            sites = detect_sites(messages)
            for site in sites:
                result.site_counts[site] += 1

            # Build canonical record
            record = {
                "messages": messages,
                "env": "LIVEWEB",
                "source": "ddb_extract",
                "score": score,
            }

            seed = extra.get("seed")
            if seed is not None:
                record["seed"] = seed

            task_id = item.get("task_id")
            if task_id is not None:
                record["template"] = f"task_{task_id}"

            records.append(record)
            result.kept += 1

        if progress_callback and result.total_scanned % 500 == 0:
            progress_callback(result.total_scanned, result.kept)

        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break

    return records, result


def write_jsonl(records: List[Dict], output_path: str) -> int:
    """Write records to JSONL file. Returns count written."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)


def format_result(result: ExtractionResult) -> str:
    """Format extraction result as human-readable summary."""
    lines = [
        f"DDB Scan: {result.total_scanned} total liveweb samples",
        f"  Score filtered (< threshold): {result.score_filtered}",
        f"  Length filtered (> max chars): {result.length_filtered}",
        f"  Decompress errors: {result.decompress_errors}",
        f"  No conversation: {result.no_conversation}",
        f"  Kept: {result.kept}",
        "",
        "Score distribution (all scanned):",
    ]
    for bucket in sorted(result.score_distribution.keys()):
        count = result.score_distribution[bucket]
        lines.append(f"  {bucket}: {count}")

    lines.append("")
    lines.append("Site coverage (kept records):")
    if result.site_counts:
        for site in sorted(result.site_counts.keys()):
            lines.append(f"  {site}: {result.site_counts[site]}")
    else:
        lines.append("  (none detected)")

    return "\n".join(lines)
