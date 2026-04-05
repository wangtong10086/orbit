"""Dataset compiler stage for VG-SOPD."""

from __future__ import annotations

import argparse
from pathlib import Path

from orbit.tasks.vg_sopd.data_utils import load_jsonl, write_json, write_jsonl
from orbit.tasks.vg_sopd.specs import CompileTaskSpec


def _conversation(prompt: str, answer: str) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": answer},
    ]


def run_compile(spec: CompileTaskSpec, *, bundle_root: str) -> dict:
    bundle_path = Path(bundle_root)
    relabelled = load_jsonl(spec.relabelled_traces_path)
    augmented = load_jsonl(spec.teacher_augmented_traces_path)
    sft_records: list[dict] = []
    preference_records: list[dict] = []
    gkd_records: list[dict] = []

    by_key = {(row["task_id"], row["sample_index"]): row for row in relabelled}
    positive_count = 0
    repaired_count = 0
    for row in augmented:
        base = by_key[(row["task_id"], row["sample_index"])]
        verifier = dict(base.get("verifier", {}))
        teacher = dict(row.get("teacher", {}))
        prompt = str(row.get("prompt", ""))
        observed = str(row.get("response", ""))
        expected = str(row.get("expected_answer", ""))
        metadata = {
            "compiler_recipe_version": spec.compile.compiler_recipe_version,
            "environment": row.get("environment", ""),
            "model_revision": spec.model_revision,
            "seed": row.get("seed", 0),
            "task_id": row.get("task_id", ""),
            "teacher_metadata": teacher.get("teacher_metadata", {}),
            "verifier_metadata": verifier.get("verifier_metadata", {}),
        }
        if verifier.get("success"):
            positive_count += 1
            sft_records.append({"messages": _conversation(prompt, observed), "metadata": metadata, "view": "positive_sft"})
        repaired = str(teacher.get("repaired_response", ""))
        if repaired:
            repaired_count += 1
            sft_records.append({"messages": _conversation(prompt, repaired), "metadata": metadata, "view": "repaired_sft"})
        if teacher.get("pairwise_preference") and repaired:
            preference_records.append(
                {
                    "messages": [{"role": "user", "content": prompt}],
                    "chosen": repaired,
                    "rejected": observed,
                    "metadata": metadata,
                }
            )
        if spec.compile.include_gkd_when_available and teacher.get("gkd_eligible") and repaired:
            gkd_records.append(
                {
                    "messages": _conversation(prompt, observed),
                    "teacher": repaired if expected else repaired,
                    "metadata": metadata,
                }
            )

    sft_path = bundle_path / "artifacts" / "compiled_sft.jsonl"
    preference_path = bundle_path / "artifacts" / "compiled_preference.jsonl"
    gkd_path = bundle_path / "artifacts" / "compiled_gkd.jsonl"
    report_path = bundle_path / "artifacts" / "iteration_report.json"
    write_jsonl(sft_path, sft_records)
    write_jsonl(preference_path, preference_records)
    if gkd_records:
        write_jsonl(gkd_path, gkd_records)
    report = {
        "compiler_recipe_version": spec.compile.compiler_recipe_version,
        "gkd_records": len(gkd_records),
        "positive_records": positive_count,
        "preference_records": len(preference_records),
        "repaired_records": repaired_count,
        "sft_records": len(sft_records),
    }
    write_json(report_path, report)
    return report


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the VG-SOPD compiler stage")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--bundle-root", required=True)
    args = parser.parse_args()
    spec = CompileTaskSpec.model_validate_json(Path(args.spec).read_text(encoding="utf-8"))
    run_compile(spec, bundle_root=args.bundle_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
