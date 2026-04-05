"""Verifier relabel and teacher augmentation stage for VG-SOPD."""

from __future__ import annotations

import argparse
from pathlib import Path

from orbit.tasks.vg_sopd.data_utils import first_error_index, load_jsonl, normalize_text, progress_score, write_json, write_jsonl
from orbit.tasks.vg_sopd.specs import RelabelTaskSpec
from orbit.tasks.vg_sopd.teacher_router import route_teacher


def run_relabel(spec: RelabelTaskSpec, *, bundle_root: str) -> dict:
    bundle_path = Path(bundle_root)
    traces = load_jsonl(spec.frontier_traces_path)
    relabelled: list[dict] = []
    augmented: list[dict] = []
    positive_count = 0
    repaired_count = 0
    gkd_count = 0
    for trace in traces:
        expected = str(trace.get("expected_answer", ""))
        observed = str(trace.get("response", ""))
        score = progress_score(expected, observed)
        success = bool(expected) and normalize_text(expected) == normalize_text(observed)
        near_miss = (not success) and score >= spec.relabel.near_miss_threshold
        teacher = route_teacher(spec.teacher_policy, str(trace.get("environment", "")).upper())
        relabelled_trace = dict(trace)
        relabelled_trace["verifier"] = {
            "score": score,
            "success": success,
            "near_miss": near_miss,
            "first_error_index": first_error_index(expected, observed) if spec.relabel.annotate_first_error and expected else -1,
            "verifier_metadata": {
                "success_threshold": spec.relabel.success_threshold,
                "near_miss_threshold": spec.relabel.near_miss_threshold,
            },
        }
        if success:
            positive_count += 1
        relabelled.append(relabelled_trace)

        augmented_trace = dict(relabelled_trace)
        repaired_response = ""
        if not success and teacher is not None:
            repaired_response = str(trace.get("teacher_repair") or expected or observed)
        score_delta = progress_score(expected, repaired_response) - score if repaired_response else 0.0
        augmented_trace["teacher"] = {
            "name": teacher.name if teacher is not None else "",
            "kind": teacher.kind if teacher is not None else "",
            "metadata": teacher.metadata if teacher is not None else {},
            "repaired_response": repaired_response,
            "score_delta": score_delta,
            "pairwise_preference": bool(repaired_response and score_delta >= spec.relabel.preference_margin),
            "gkd_eligible": bool(teacher is not None and teacher.kind == "white_box" and repaired_response),
            "teacher_metadata": {
                "policy_applied": teacher.name if teacher is not None else "",
            },
        }
        if repaired_response:
            repaired_count += 1
        if augmented_trace["teacher"]["gkd_eligible"]:
            gkd_count += 1
        augmented.append(augmented_trace)

    relabel_path = bundle_path / "artifacts" / "relabelled_traces.jsonl"
    teacher_path = bundle_path / "artifacts" / "teacher_augmented_traces.jsonl"
    summary_path = bundle_path / "artifacts" / "relabel_summary.json"
    write_jsonl(relabel_path, relabelled)
    write_jsonl(teacher_path, augmented)
    summary = {
        "gkd_eligible_count": gkd_count,
        "positive_count": positive_count,
        "record_count": len(relabelled),
        "repaired_count": repaired_count,
    }
    write_json(summary_path, summary)
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the VG-SOPD relabel stage")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--bundle-root", required=True)
    args = parser.parse_args()
    spec = RelabelTaskSpec.model_validate_json(Path(args.spec).read_text(encoding="utf-8"))
    run_relabel(spec, bundle_root=args.bundle_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
