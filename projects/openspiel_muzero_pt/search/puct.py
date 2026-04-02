from __future__ import annotations

from typing import Iterable

import numpy as np

from .tree import SearchEdge, SearchNode


def puct_score(edge: SearchEdge, *, parent_visit_count: int, c_puct: float, maximize_root: bool) -> float:
    q_term = edge.q_root if maximize_root else -edge.q_root
    u_term = float(c_puct) * float(edge.prior) * np.sqrt(float(parent_visit_count + 1)) / float(edge.visit_count + 1)
    return q_term + u_term


def select_child(node: SearchNode, *, c_puct: float) -> SearchEdge:
    candidates = node.candidate_edges()
    if not candidates:
        raise RuntimeError("Cannot select a child from an unexpanded node without candidate edges")
    maximize_root = int(node.current_player) == int(node.root_player)
    parent_visit_count = sum(edge.visit_count for edge in candidates)
    return max(
        candidates,
        key=lambda edge: puct_score(
            edge,
            parent_visit_count=parent_visit_count,
            c_puct=c_puct,
            maximize_root=maximize_root,
        ),
    )


def backup_edges(path: list[SearchEdge], value_root: float) -> None:
    value_root = float(value_root)
    for edge in path:
        edge.visit_count += 1
        edge.value_sum += value_root
