from __future__ import annotations

import numpy as np

from projects.openspiel_muzero_pt.search.gumbel_root import SequentialHalvingController
from projects.openspiel_muzero_pt.search.tree import SearchEdge, SearchNode


def test_sequential_halving_reduces_root_candidate_set():
    legal = np.arange(12, dtype=np.int64)
    gumbel_scores = np.linspace(0.0, 1.0, num=12, dtype=np.float32)
    controller = SequentialHalvingController.build(
        legal_actions=legal,
        shortlisted_actions=legal,
        gumbel_scores=gumbel_scores,
        total_simulations=32,
        fallback_threshold=8,
    )
    root = SearchNode(
        state=None,
        latent=None,
        policy_logits=None,
        legal_mask=np.ones((12,), dtype=np.float32),
        root_player=0,
        current_player=0,
        depth=0,
        terminal=False,
        network_value_root=0.0,
    )
    root.edges = {
        int(action): SearchEdge(action=int(action), prior=1.0 / 12.0, visit_count=1, value_sum=float(action))
        for action in legal
    }
    assert controller.candidate_actions().shape[0] == 12

    root.edges[0].visit_count = 3
    root.edges[1].visit_count = 3
    root.edges[2].visit_count = 3
    root.edges[3].visit_count = 3
    root.edges[4].visit_count = 3
    root.edges[5].visit_count = 3
    root.edges[6].visit_count = 3
    root.edges[7].visit_count = 3
    root.edges[8].visit_count = 3
    root.edges[9].visit_count = 3
    root.edges[10].visit_count = 3
    root.edges[11].visit_count = 3
    controller.maybe_advance(root)
    assert controller.candidate_actions().shape[0] < 12


def test_sequential_halving_falls_back_when_budget_is_too_small():
    legal = np.arange(10, dtype=np.int64)
    controller = SequentialHalvingController.build(
        legal_actions=legal,
        shortlisted_actions=legal,
        gumbel_scores=np.linspace(0.0, 1.0, num=10, dtype=np.float32),
        total_simulations=8,
        fallback_threshold=8,
    )
    assert controller.stage_targets == []
    assert controller.stage_keep_counts == []
    assert controller.candidate_actions().shape[0] == 10
