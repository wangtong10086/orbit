from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RootSelection:
    actions: np.ndarray
    priors: np.ndarray
    gumbel_scores: np.ndarray


def select_gumbel_root_actions(
    priors: np.ndarray,
    legal_mask: np.ndarray,
    *,
    max_num_considered_actions: int,
    rng: np.random.Generator,
) -> RootSelection:
    legal_actions = np.flatnonzero(np.asarray(legal_mask, dtype=np.float32) > 0)
    if legal_actions.size == 0:
        return RootSelection(
            actions=np.zeros((0,), dtype=np.int64),
            priors=np.zeros_like(legal_mask, dtype=np.float32),
            gumbel_scores=np.full_like(legal_mask, fill_value=-np.inf, dtype=np.float32),
        )
    priors = np.asarray(priors, dtype=np.float32)
    masked = np.zeros_like(legal_mask, dtype=np.float32)
    masked[legal_actions] = priors[legal_actions]
    total = float(masked.sum())
    if total <= 0:
        masked[legal_actions] = 1.0 / float(legal_actions.size)
    else:
        masked /= total
    all_scores = np.full_like(masked, fill_value=-np.inf, dtype=np.float32)
    if legal_actions.size <= max_num_considered_actions:
        all_scores[legal_actions] = np.log(np.clip(masked[legal_actions], 1e-8, None))
        return RootSelection(actions=legal_actions.astype(np.int64), priors=masked, gumbel_scores=all_scores)
    gumbels = rng.gumbel(size=legal_actions.size).astype(np.float32)
    scores = np.log(np.clip(masked[legal_actions], 1e-8, None)) + gumbels
    all_scores[legal_actions] = scores
    shortlist = legal_actions[np.argsort(scores)[-int(max_num_considered_actions) :]]
    shortlist = np.sort(shortlist.astype(np.int64))
    return RootSelection(actions=shortlist, priors=masked, gumbel_scores=all_scores)


@dataclass(slots=True)
class SequentialHalvingController:
    active_actions: np.ndarray
    gumbel_scores: np.ndarray
    stage_targets: list[int]
    stage_keep_counts: list[int]
    current_stage: int = 0

    @classmethod
    def build(
        cls,
        *,
        legal_actions: np.ndarray,
        shortlisted_actions: np.ndarray,
        gumbel_scores: np.ndarray,
        total_simulations: int,
        fallback_threshold: int = 8,
    ) -> "SequentialHalvingController":
        legal_actions = np.asarray(legal_actions, dtype=np.int64)
        shortlisted_actions = np.asarray(shortlisted_actions, dtype=np.int64)
        if (
            legal_actions.size <= fallback_threshold
            or shortlisted_actions.size <= 1
            or total_simulations <= 1
            or total_simulations < (2 * int(shortlisted_actions.size))
        ):
            return cls(
                active_actions=shortlisted_actions if shortlisted_actions.size > 0 else legal_actions,
                gumbel_scores=np.asarray(gumbel_scores, dtype=np.float32),
                stage_targets=[],
                stage_keep_counts=[],
            )
        active_count = int(shortlisted_actions.size)
        remaining_budget = int(total_simulations)
        targets: list[int] = []
        keep_counts: list[int] = []
        cumulative = 0
        while active_count > 1 and remaining_budget > 0:
            next_count = max((active_count + 1) // 2, 1)
            stages_left = max(int(np.ceil(np.log2(active_count))), 1)
            sims_per_action = max(1, remaining_budget // max(active_count * stages_left, 1))
            stage_budget = min(remaining_budget, sims_per_action * active_count)
            cumulative += stage_budget
            targets.append(cumulative)
            keep_counts.append(next_count)
            remaining_budget -= stage_budget
            active_count = next_count
        return cls(
            active_actions=shortlisted_actions if shortlisted_actions.size > 0 else legal_actions,
            gumbel_scores=np.asarray(gumbel_scores, dtype=np.float32),
            stage_targets=targets,
            stage_keep_counts=keep_counts,
        )

    def candidate_actions(self) -> np.ndarray:
        return self.active_actions

    def maybe_advance(self, root) -> None:
        while self.current_stage < len(self.stage_targets) and int(root.visit_count) >= int(self.stage_targets[self.current_stage]):
            keep_count = int(self.stage_keep_counts[self.current_stage])
            if self.active_actions.size <= keep_count:
                self.current_stage += 1
                continue
            ranked = sorted(
                (int(action) for action in self.active_actions),
                key=lambda action: (
                    float(root.edges[action].q_root) if action in root.edges else -np.inf,
                    float(root.edges[action].visit_count) if action in root.edges else 0.0,
                    float(self.gumbel_scores[action]) if np.isfinite(self.gumbel_scores[action]) else -np.inf,
                ),
                reverse=True,
            )
            self.active_actions = np.asarray(ranked[:keep_count], dtype=np.int64)
            self.current_stage += 1
