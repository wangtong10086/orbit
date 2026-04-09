"""Static-trace verifier implementation."""

from __future__ import annotations

import hashlib
import json

from orbit.foundation.task_data import (
    assistant_text,
    detect_switch_step,
    discounted_returns,
    first_error_index,
    normalize_steps,
    normalize_text,
    padded_floats,
    progress_score,
)
from orbit.verifiers.base import VerifierResult, VerifierSpec


class StaticTraceVerifier:
    def __init__(self, spec: VerifierSpec, *, success_threshold: float = 0.99, near_miss_threshold: float = 0.5):
        self.spec = spec
        self.success_threshold = success_threshold
        self.near_miss_threshold = near_miss_threshold

    def verify(self, trace: dict) -> VerifierResult:
        expected = str(trace.get("expected_answer", ""))
        student_steps = normalize_steps(trace.get("student_steps"))
        observed = assistant_text(student_steps) or str(trace.get("response", ""))
        verifier_trace = dict(trace.get("verifier_trace", {}) or {})
        derived_step_scores = [progress_score(expected, assistant_text(student_steps[: idx + 1])) for idx in range(max(len(student_steps), 1))]
        if not student_steps:
            derived_step_scores = [progress_score(expected, observed)]
        potentials = padded_floats(verifier_trace.get("potentials") or derived_step_scores, length=max(len(student_steps), 1))
        local_scores = padded_floats(
            verifier_trace.get("local_scores") or derived_step_scores,
            length=max(len(student_steps), 1),
            default=potentials[-1] if potentials else 0.0,
        )
        env_rewards = padded_floats(verifier_trace.get("env_rewards"), length=max(len(student_steps), 1))
        terminal_score = float(verifier_trace.get("terminal_utility", progress_score(expected, observed)) or 0.0)
        success = terminal_score >= self.success_threshold or (bool(expected) and normalize_text(expected) == normalize_text(observed))
        near_miss = (not success) and terminal_score >= self.near_miss_threshold
        switch_step = detect_switch_step(
            explicit_switch_step=trace.get("switch_step"),
            local_scores=local_scores,
            potentials=potentials,
            success_threshold=self.success_threshold,
        )
        phi_prefix = [0.0]
        phi_prefix.extend(potentials)
        process_rewards = []
        for idx in range(len(local_scores)):
            reward = (
                self.spec.lambda_delta * (phi_prefix[idx + 1] - phi_prefix[idx])
                + self.spec.lambda_g * local_scores[idx]
                + self.spec.lambda_env * env_rewards[idx]
            )
            if idx == len(local_scores) - 1:
                reward += self.spec.lambda_u * terminal_score
            process_rewards.append(reward)
        process_returns = discounted_returns(process_rewards, gamma=self.spec.gamma)
        if self.spec.baseline_strategy == "trajectory_mean" and len(process_returns) > 1:
            baseline = sum(process_returns) / len(process_returns)
        else:
            baseline = 0.0
        process_weights = []
        for value in process_returns:
            weight = (value - baseline) / max(self.spec.process_weight_scale, 1e-6)
            process_weights.append(max(-self.spec.process_weight_max, min(self.spec.process_weight_max, weight)))
        return VerifierResult(
            terminal_score=terminal_score,
            success=success,
            near_miss=near_miss,
            first_error_index=first_error_index(expected, observed) if expected else -1,
            switch_step=switch_step,
            potentials=tuple(potentials),
            local_scores=tuple(local_scores),
            env_rewards=tuple(env_rewards),
            process_rewards=tuple(process_rewards),
            process_returns=tuple(process_returns),
            process_weights=tuple(process_weights),
            baseline=baseline,
            metadata={
                "success_threshold": self.success_threshold,
                "near_miss_threshold": self.near_miss_threshold,
                "gamma": self.spec.gamma,
                "lambda_delta": self.spec.lambda_delta,
                "lambda_g": self.spec.lambda_g,
                "lambda_env": self.spec.lambda_env,
                "lambda_u": self.spec.lambda_u,
            },
        )

    def locate_first_error(self, expected: str, observed: str) -> int:
        return first_error_index(expected, observed)

    def state_hash(self, trace: dict) -> str:
        payload = {
            "environment": trace.get("environment", ""),
            "task_id": trace.get("task_id", ""),
            "prompt": trace.get("prompt", ""),
            "response": trace.get("response", ""),
            "student_steps": trace.get("student_steps", []),
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


__all__ = ["StaticTraceVerifier"]
