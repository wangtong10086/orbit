"""Build normalized ms-swift training datasets from canonical JSONL files."""

from __future__ import annotations

import json
from pathlib import Path

from orbit.foundation.packing import Qwen3ConversationPacker
from orbit.foundation.repository import ENV_FILENAME_MAP


_FILENAME_TO_ENV = {filename: env_name for env_name, filename in ENV_FILENAME_MAP.items()}


def infer_env_name(path: str | Path) -> str:
    filename = Path(path).name
    return _FILENAME_TO_ENV.get(filename, Path(filename).stem.upper().replace("_", "-"))


def normalize_record_for_ms_swift(record: dict, *, default_env_name: str = "") -> dict:
    normalized = dict(record)
    if default_env_name and not normalized.get("env"):
        normalized["env"] = default_env_name
    packed = Qwen3ConversationPacker(default_env_name=default_env_name).pack(normalized)
    if not packed:
        raise ValueError("record does not contain packable messages")
    return {"messages": packed}


def build_ms_swift_dataset(
    *,
    input_paths: list[str | Path],
    output_path: str | Path,
    manifest_path: str | Path | None = None,
) -> dict:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_target = Path(manifest_path) if manifest_path else None
    counts_by_file: dict[str, int] = {}
    skipped_by_file: dict[str, int] = {}
    total = 0
    skipped_total = 0

    with output.open("w", encoding="utf-8") as out:
        for raw_path in input_paths:
            source = Path(raw_path)
            env_name = infer_env_name(source)
            written = 0
            skipped = 0
            with source.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        normalized = normalize_record_for_ms_swift(record, default_env_name=env_name)
                    except Exception:
                        skipped += 1
                        continue
                    out.write(json.dumps(normalized, ensure_ascii=False) + "\n")
                    written += 1
            counts_by_file[str(source)] = written
            skipped_by_file[str(source)] = skipped
            total += written
            skipped_total += skipped

    manifest = {
        "input_paths": [str(Path(path)) for path in input_paths],
        "output_path": str(output),
        "total": total,
        "skipped_total": skipped_total,
        "counts_by_file": counts_by_file,
        "skipped_by_file": skipped_by_file,
    }
    if manifest_target is not None:
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


__all__ = [
    "build_ms_swift_dataset",
    "infer_env_name",
    "normalize_record_for_ms_swift",
]
