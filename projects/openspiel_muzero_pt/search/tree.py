from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class SearchEdge:
    action: int
    prior: float
    visit_count: int = 0
    value_sum: float = 0.0
    child: "SearchNode | None" = None

    @property
    def q_root(self) -> float:
        if self.visit_count <= 0:
            return 0.0
        return self.value_sum / float(self.visit_count)


@dataclass(slots=True)
class SearchNode:
    state: Any
    latent: Any
    policy_logits: np.ndarray | None
    legal_mask: np.ndarray
    root_player: int
    current_player: int
    depth: int
    terminal: bool = False
    network_value_root: float = 0.0
    root_shortlist: np.ndarray | None = None
    root_gumbel_scores: np.ndarray | None = None
    edges: dict[int, SearchEdge] = field(default_factory=dict)
    expanded: bool = False

    def expand(self, priors: np.ndarray) -> None:
        if self.expanded or self.terminal:
            self.expanded = True
            return
        priors = np.asarray(priors, dtype=np.float32)
        legal_actions = np.flatnonzero(self.legal_mask > 0)
        if legal_actions.size == 0:
            self.expanded = True
            return
        masked = np.zeros_like(self.legal_mask, dtype=np.float32)
        masked[legal_actions] = priors[legal_actions]
        total = float(masked.sum())
        if total <= 0:
            masked[legal_actions] = 1.0 / float(legal_actions.size)
        else:
            masked /= total
        self.edges = {int(action): SearchEdge(action=int(action), prior=float(masked[action])) for action in legal_actions}
        self.expanded = True

    def sync_priors(self, priors: np.ndarray) -> None:
        if self.terminal:
            self.expanded = True
            return
        priors = np.asarray(priors, dtype=np.float32)
        legal_actions = np.flatnonzero(self.legal_mask > 0)
        if legal_actions.size == 0:
            self.edges = {}
            self.expanded = True
            return
        masked = np.zeros_like(self.legal_mask, dtype=np.float32)
        masked[legal_actions] = priors[legal_actions]
        total = float(masked.sum())
        if total <= 0:
            masked[legal_actions] = 1.0 / float(legal_actions.size)
        else:
            masked /= total
        previous = self.edges
        self.edges = {}
        for action in legal_actions:
            action = int(action)
            if action in previous:
                edge = previous[action]
                edge.prior = float(masked[action])
                self.edges[action] = edge
            else:
                self.edges[action] = SearchEdge(action=action, prior=float(masked[action]))
        self.expanded = True

    @property
    def visit_count(self) -> int:
        return int(sum(edge.visit_count for edge in self.edges.values()))

    @property
    def tree_node_count(self) -> int:
        total = 1
        for edge in self.edges.values():
            if edge.child is not None:
                total += edge.child.tree_node_count
        return total

    def candidate_edges(self) -> list[SearchEdge]:
        if self.depth == 0 and self.root_shortlist is not None and len(self.root_shortlist) > 0:
            shortlisted = [self.edges[int(action)] for action in self.root_shortlist if int(action) in self.edges]
            if shortlisted:
                return shortlisted
        return list(self.edges.values())


def reroot_subtree(node: SearchNode, *, new_root_player: int, depth: int, sign: float, reset_root_metadata: bool) -> SearchNode:
    node.root_player = int(new_root_player)
    node.depth = int(depth)
    node.network_value_root = float(node.network_value_root) * float(sign)
    if reset_root_metadata:
        node.root_shortlist = None
        node.root_gumbel_scores = None
    for edge in node.edges.values():
        edge.value_sum *= float(sign)
        if edge.child is not None:
            reroot_subtree(
                edge.child,
                new_root_player=int(new_root_player),
                depth=depth + 1,
                sign=float(sign),
                reset_root_metadata=False,
            )
    return node
