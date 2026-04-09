"""Task-source evaluation for frozen ablation splits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from orbit.foundation.task_data import load_jsonl, normalize_messages, write_json, write_jsonl
from orbit.verifiers.base import VerifierSpec
from orbit.verifiers.static import StaticTraceVerifier

try:  # pragma: no cover - optional import path exercised in real runs
    from peft import AutoPeftModelForCausalLM
except Exception:  # pragma: no cover
    AutoPeftModelForCausalLM = None


def _chat_text(tokenizer, messages: list[dict[str, str]], *, add_generation_prompt: bool) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=add_generation_prompt)
        except Exception:
            pass
    rendered = []
    for message in messages:
        rendered.append(f"{message.get('role', 'user')}: {message.get('content', '')}")
    if add_generation_prompt:
        rendered.append("assistant:")
    return "\n".join(rendered)


def _adapter_base_model(model_ref: str) -> str:
    config_path = Path(model_ref) / "adapter_config.json"
    if not config_path.exists():
        return ""
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return str(payload.get("base_model_name_or_path", "") or "")


def _tokenizer_source(model_ref: str) -> str:
    target = Path(model_ref)
    if (target / "tokenizer_config.json").exists() or (target / "tokenizer.json").exists():
        return str(target)
    base_model = _adapter_base_model(model_ref)
    return base_model or model_ref


def _load_model_and_tokenizer(model_ref: str):
    tokenizer = AutoTokenizer.from_pretrained(_tokenizer_source(model_ref), trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token
    model_kwargs = {"trust_remote_code": True}
    if torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.bfloat16
    adapter_config = Path(model_ref) / "adapter_config.json"
    if adapter_config.exists():
        if AutoPeftModelForCausalLM is None:
            raise RuntimeError("peft is required to evaluate adapter checkpoints")
        model = AutoPeftModelForCausalLM.from_pretrained(model_ref, **model_kwargs)
    else:
        model = AutoModelForCausalLM.from_pretrained(model_ref, **model_kwargs)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()
    return model, tokenizer, device


def _generate_response(model, tokenizer, device: str, messages: list[dict[str, str]], *, max_new_tokens: int, temperature: float) -> str:
    prompt = _chat_text(tokenizer, messages, add_generation_prompt=True)
    encoded = tokenizer(prompt, return_tensors="pt")
    encoded = {key: value.to(device) for key, value in encoded.items()}
    generate_kwargs = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if temperature > 0:
        generate_kwargs["do_sample"] = True
        generate_kwargs["temperature"] = temperature
    else:
        generate_kwargs["do_sample"] = False
    with torch.inference_mode():
        output = model.generate(**encoded, **generate_kwargs)
    new_tokens = output[0][encoded["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def evaluate_task_source_model(
    *,
    model_ref: str,
    task_source_path: str,
    output_dir: str,
    seed: int = 42,
    max_new_tokens: int = 64,
    temperature: float = 0.0,
) -> dict:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    model, tokenizer, device = _load_model_and_tokenizer(model_ref)
    verifier = StaticTraceVerifier(VerifierSpec())
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(task_source_path)
    predictions: list[dict] = []
    per_env: dict[str, dict[str, float]] = {}
    for raw in records:
        environment = str(raw.get("environment", raw.get("env", "")) or "").upper()
        prompt = str(raw.get("prompt", ""))
        messages = normalize_messages(raw.get("messages"), prompt=prompt)
        response = _generate_response(
            model,
            tokenizer,
            device,
            messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        trace = {
            "environment": environment,
            "task_id": str(raw.get("task_id", "")),
            "prompt": prompt,
            "expected_answer": str(raw.get("expected_answer", "")),
            "response": response,
            "student_steps": [{"role": "assistant", "content": response}],
            "verifier_trace": dict(raw.get("verifier_trace", {}) or {}),
            "switch_step": raw.get("switch_step"),
        }
        result = verifier.verify(trace)
        bucket = per_env.setdefault(
            environment,
            {"sample_count": 0, "success_count": 0, "terminal_score_sum": 0.0},
        )
        bucket["sample_count"] += 1
        bucket["success_count"] += 1 if result.success else 0
        bucket["terminal_score_sum"] += float(result.terminal_score)
        predictions.append(
            {
                "environment": environment,
                "task_id": trace["task_id"],
                "prompt": prompt,
                "expected_answer": trace["expected_answer"],
                "response": response,
                "success": result.success,
                "terminal_score": result.terminal_score,
                "first_error_index": result.first_error_index,
                "model": model_ref,
            }
        )

    results = {}
    for env_name, stats in per_env.items():
        sample_count = int(stats["sample_count"])
        success_count = int(stats["success_count"])
        success_rate = (success_count / sample_count) if sample_count else 0.0
        mean_terminal_score = (float(stats["terminal_score_sum"]) / sample_count) if sample_count else 0.0
        results[env_name] = {
            "sample_count": sample_count,
            "success_count": success_count,
            "success_rate": success_rate,
            "mean_score": success_rate,
            "mean_terminal_score": mean_terminal_score,
        }

    summary = {
        "model": model_ref,
        "task_source_path": task_source_path,
        "seed": seed,
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
        "results": results,
    }
    write_jsonl(output_root / "predictions.jsonl", predictions)
    write_json(output_root / "eval_summary.json", summary)
    return summary


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a model checkpoint on a frozen task-source split")
    parser.add_argument("--model", required=True)
    parser.add_argument("--task-source", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args(list(argv) if argv is not None else None)
    evaluate_task_source_model(
        model_ref=args.model,
        task_source_path=args.task_source,
        output_dir=args.output_dir,
        seed=args.seed,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
