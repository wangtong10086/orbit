from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import numpy as np
import torch

from projects.openspiel_muzero_pt.games.adapters import AffineOpenSpielAdapter
from projects.openspiel_muzero_pt.games.action_codecs import get_action_codec
from projects.openspiel_muzero_pt.runtime.inference import ModelInferenceClient

from .gumbel_root import SequentialHalvingController, select_gumbel_root_actions
from .puct import backup_edges, select_child
from .tree import SearchEdge, SearchNode, reroot_subtree


@dataclass(frozen=True, slots=True)
class SearchConfig:
    train_num_simulations: int = 64
    reanalyse_num_simulations: int = 128
    eval_num_simulations: int = 128
    c_puct: float = 1.5
    root_dirichlet_epsilon: float = 0.25
    max_num_considered_actions: int = 32
    leaf_batch_size: int = 16
    seed: int = 0

    def simulations_for_mode(self, mode: str) -> int:
        if mode == "selfplay":
            return self.train_num_simulations
        if mode == "reanalyse":
            return self.reanalyse_num_simulations
        if mode == "eval":
            return self.eval_num_simulations
        raise KeyError(f"Unsupported search mode: {mode}")


@dataclass(slots=True)
class SearchStats:
    n_legal: int
    selected_depth_mean: float
    tree_nodes: int
    search_time_ms: float
    value_range: tuple[float, float]
    entropy: float


@dataclass(slots=True)
class SearchResultBatch:
    root_policy: np.ndarray
    root_value: np.ndarray
    chosen_action: np.ndarray
    stats: list[SearchStats]
    root_nodes: list[SearchNode | None]


@dataclass(slots=True)
class PendingExpansion:
    root_index: int
    parent_node: SearchNode
    edge: SearchEdge
    state: Any
    encoded_obs: np.ndarray | None
    legal_mask: np.ndarray
    current_player: int
    terminal: bool
    path: list[SearchEdge]


class SearchEngine:
    def __init__(
        self,
        *,
        inference_client: ModelInferenceClient,
        adapter: AffineOpenSpielAdapter,
        config: SearchConfig,
        device=None,
    ):
        self.inference_client = inference_client
        self.adapter = adapter
        self.config = config
        self.codec = get_action_codec(adapter.spec)
        self.rng = np.random.default_rng(config.seed)

    def run(
        self,
        obs_batch,
        legal_mask_batch,
        game_state_batch: list[Any],
        mode: str,
        encoded_state_batch: list[Any] | None = None,
        root_nodes: list[SearchNode | None] | None = None,
    ) -> SearchResultBatch:
        start = time.perf_counter()
        simulations = self.config.simulations_for_mode(mode)
        encoded_batch = list(encoded_state_batch) if encoded_state_batch is not None else [self.adapter.encode_state(state) for state in game_state_batch]
        reusable_roots = list(root_nodes) if root_nodes is not None else [None] * len(game_state_batch)
        root_initial = None
        init_indices: list[int] = []
        init_obs: list[np.ndarray] = []
        for index, reusable_root in enumerate(reusable_roots):
            encoded = encoded_batch[index]
            if reusable_root is None or encoded.terminal:
                init_indices.append(index)
                init_obs.append(encoded.obs)
        if init_obs:
            obs_np = np.stack(init_obs).astype(np.float32, copy=False)
            root_initial = self.inference_client.initial(obs_np)
        roots: list[SearchNode] = []
        root_controllers: list[SequentialHalvingController | None] = []
        rollout_depths: list[list[int]] = [[] for _ in game_state_batch]
        init_output_index = 0

        for index, state in enumerate(game_state_batch):
            encoded = encoded_batch[index]
            if encoded.terminal:
                root_value = self.adapter.current_player_view_value(state, 0)
                node = SearchNode(
                    state=state.clone(),
                    latent=None,
                    policy_logits=None,
                    legal_mask=encoded.legal_mask,
                    root_player=0,
                    current_player=-1,
                    depth=0,
                    terminal=True,
                    network_value_root=float(root_value),
                )
                roots.append(node)
                root_controllers.append(None)
                continue
            reusable_root = reusable_roots[index]
            if reusable_root is not None:
                root_player = int(state.current_player())
                node = reroot_subtree(
                    reusable_root,
                    new_root_player=root_player,
                    depth=0,
                    sign=1.0,
                    reset_root_metadata=True,
                )
                node.state = state.clone()
                node.legal_mask = encoded.legal_mask
                node.current_player = root_player
            else:
                root_player = int(state.current_player())
                if root_initial is None:
                    raise RuntimeError("Missing initial inference output for fresh root")
                node = SearchNode(
                    state=state.clone(),
                    latent=root_initial.latent[init_output_index : init_output_index + 1].copy(),
                    policy_logits=root_initial.policy_logits[init_output_index].copy(),
                    legal_mask=encoded.legal_mask,
                    root_player=root_player,
                    current_player=root_player,
                    depth=0,
                    terminal=False,
                    network_value_root=float(root_initial.value[init_output_index]),
                )
                init_output_index += 1
            priors = self._root_priors(node.policy_logits, encoded.legal_mask, mode=mode)
            node.sync_priors(priors)
            shortlist = select_gumbel_root_actions(
                priors,
                encoded.legal_mask,
                max_num_considered_actions=self.config.max_num_considered_actions,
                rng=self.rng,
            )
            node.root_shortlist = shortlist.actions
            node.root_gumbel_scores = shortlist.gumbel_scores
            roots.append(node)
            legal_actions = np.flatnonzero(encoded.legal_mask > 0)
            root_controllers.append(
                SequentialHalvingController.build(
                    legal_actions=legal_actions,
                    shortlisted_actions=shortlist.actions,
                    gumbel_scores=shortlist.gumbel_scores,
                    total_simulations=simulations,
                )
            )

        for _ in range(simulations):
            for root, controller in zip(roots, root_controllers):
                if controller is None:
                    continue
                controller.maybe_advance(root)
                root.root_shortlist = controller.candidate_actions()
            pending = self._collect_pending_expansions(roots, rollout_depths)
            self._resolve_pending_expansions(pending)

        policies = []
        root_values = []
        chosen_actions = []
        stats = []
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        for index, root in enumerate(roots):
            policy = self._gumbel_improved_policy(root)
            legal_count = int((root.legal_mask > 0).sum())
            chosen = self._choose_action(policy, encoded_batch[index].phase, mode=mode)
            q_values = [edge.q_root for edge in root.edges.values()] if root.edges else [float(root.network_value_root)]
            entropy = float(-(policy[policy > 0] * np.log(np.clip(policy[policy > 0], 1e-8, None))).sum())
            stats.append(
                SearchStats(
                    n_legal=legal_count,
                    selected_depth_mean=float(np.mean(rollout_depths[index])) if rollout_depths[index] else 0.0,
                    tree_nodes=root.tree_node_count,
                    search_time_ms=elapsed_ms / max(len(roots), 1),
                    value_range=(float(min(q_values)), float(max(q_values))),
                    entropy=entropy,
                )
            )
            policies.append(policy)
            if root.edges and policy.sum() > 0:
                weighted_value = 0.0
                for action, edge in root.edges.items():
                    weighted_value += float(policy[int(action)]) * float(edge.q_root)
                root_values.append(float(weighted_value))
            else:
                root_values.append(float(root.network_value_root))
            chosen_actions.append(int(chosen))
        return SearchResultBatch(
            root_policy=np.stack(policies).astype(np.float32),
            root_value=np.asarray(root_values, dtype=np.float32),
            chosen_action=np.asarray(chosen_actions, dtype=np.int64),
            stats=stats,
            root_nodes=roots,
        )

    def promote_child_root(
        self,
        *,
        root: SearchNode | None,
        action: int,
        next_state: Any,
    ) -> SearchNode | None:
        if root is None or root.terminal or next_state.is_terminal():
            return None
        edge = root.edges.get(int(action))
        if edge is None or edge.child is None:
            return None
        child = edge.child
        new_root_player = int(next_state.current_player())
        sign = 1.0 if int(root.root_player) == int(new_root_player) else -1.0
        rerooted = reroot_subtree(
            child,
            new_root_player=new_root_player,
            depth=0,
            sign=sign,
            reset_root_metadata=True,
        )
        rerooted.state = next_state.clone()
        rerooted.current_player = new_root_player
        return rerooted

    def _collect_pending_expansions(self, roots: list[SearchNode], rollout_depths: list[list[int]]) -> list[PendingExpansion]:
        pending: list[PendingExpansion] = []
        for root_index, root in enumerate(roots):
            if root.terminal:
                continue
            node = root
            path: list[SearchEdge] = []
            depth = 0
            while True:
                if node.terminal or not node.edges:
                    break
                edge = select_child(node, c_puct=self.config.c_puct)
                path.append(edge)
                depth += 1
                if edge.child is None:
                    child_state = node.state.clone()
                    self.adapter.apply_dense_action(child_state, edge.action)
                    if child_state.is_terminal():
                        pending.append(
                            PendingExpansion(
                                root_index=root_index,
                                parent_node=node,
                                edge=edge,
                                state=child_state,
                                encoded_obs=None,
                                legal_mask=np.zeros((self.adapter.spec.action_dim,), dtype=np.float32),
                                current_player=-1,
                                terminal=True,
                                path=list(path),
                            )
                        )
                    else:
                        encoded = self.adapter.encode_state(child_state)
                        pending.append(
                            PendingExpansion(
                                root_index=root_index,
                                parent_node=node,
                                edge=edge,
                                state=child_state,
                                encoded_obs=encoded.obs,
                                legal_mask=encoded.legal_mask,
                                current_player=encoded.current_player,
                                terminal=False,
                                path=list(path),
                            )
                        )
                    rollout_depths[root_index].append(depth)
                    break
                node = edge.child
                if node.terminal:
                    rollout_depths[root_index].append(depth)
                    pending.append(
                        PendingExpansion(
                            root_index=root_index,
                            parent_node=node,
                            edge=edge,
                            state=node.state,
                            encoded_obs=None,
                            legal_mask=node.legal_mask,
                            current_player=node.current_player,
                            terminal=True,
                            path=list(path),
                        )
                    )
                    break
        return pending

    def _resolve_pending_expansions(self, pending: list[PendingExpansion]) -> None:
        if not pending:
            return
        nonterminal = [item for item in pending if not item.terminal]
        outputs: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        if nonterminal:
            parent_latents = np.concatenate([item.parent_node.latent for item in nonterminal], axis=0).astype(np.float32, copy=False)
            action_tensor = (
                self.codec.batch_action_planes(
                    [item.edge.action for item in nonterminal],
                    self.adapter.spec,
                    device="cpu",
                )
                .numpy()
                .astype(np.float32, copy=False)
            )
            recurrent = self.inference_client.recurrent(parent_latents, action_tensor)
            outputs = list(
                zip(
                    np.split(recurrent.latent, recurrent.latent.shape[0], axis=0),
                    recurrent.reward,
                    recurrent.policy_logits,
                    recurrent.value,
                )
            )
        output_index = 0
        for item in pending:
            if item.terminal:
                child = SearchNode(
                    state=item.state.clone(),
                    latent=None,
                    policy_logits=None,
                    legal_mask=item.legal_mask,
                    root_player=item.parent_node.root_player,
                    current_player=-1,
                    depth=item.parent_node.depth + 1,
                    terminal=True,
                    network_value_root=float(item.state.returns()[item.parent_node.root_player]),
                )
                item.edge.child = child
                backup_edges(item.path, child.network_value_root)
                continue
            latent, reward, policy_logits, value = outputs[output_index]
            output_index += 1
            value_scalar = float(np.asarray(value).item())
            if int(item.current_player) != int(item.parent_node.root_player):
                value_scalar = -value_scalar
            child = SearchNode(
                state=item.state.clone(),
                latent=np.asarray(latent, dtype=np.float32),
                policy_logits=np.asarray(policy_logits, dtype=np.float32),
                legal_mask=item.legal_mask,
                root_player=item.parent_node.root_player,
                current_player=item.current_player,
                depth=item.parent_node.depth + 1,
                terminal=False,
                network_value_root=value_scalar,
            )
            priors = self._masked_priors(child.policy_logits, child.legal_mask)
            child.expand(priors)
            item.edge.child = child
            backup_edges(item.path, child.network_value_root)

    def _masked_priors(self, policy_logits: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
        logits = np.asarray(policy_logits, dtype=np.float32).copy()
        illegal = legal_mask <= 0
        logits[illegal] = -1e9
        logits -= float(np.max(logits))
        probs = np.exp(logits)
        probs[illegal] = 0.0
        total = float(probs.sum())
        if total <= 0:
            legal = np.flatnonzero(~illegal)
            if legal.size > 0:
                probs[legal] = 1.0 / float(legal.size)
            return probs.astype(np.float32)
        return (probs / total).astype(np.float32)

    def _root_priors(self, policy_logits: np.ndarray, legal_mask: np.ndarray, *, mode: str) -> np.ndarray:
        priors = self._masked_priors(policy_logits, legal_mask)
        if mode != "selfplay":
            return priors
        # Gumbel MuZero: exploration comes from Gumbel noise in sequential halving,
        # not from Dirichlet root noise.  Skip Dirichlet when epsilon <= 0.
        if self.config.root_dirichlet_epsilon <= 0.0:
            return priors
        legal = np.flatnonzero(legal_mask > 0)
        if legal.size == 0:
            return priors
        alpha = float(np.clip(10.0 / float(legal.size), 0.03, 0.30))
        noise = self.rng.dirichlet(np.full((legal.size,), alpha, dtype=np.float32))
        blended = priors.copy()
        blended[legal] = (
            (1.0 - self.config.root_dirichlet_epsilon) * blended[legal]
            + self.config.root_dirichlet_epsilon * noise.astype(np.float32)
        )
        return blended

    def _gumbel_improved_policy(self, root: "SearchNode") -> np.ndarray:
        """Gumbel MuZero improved policy (Danihelka et al. 2022, Eq. 6).

        Instead of normalized visit counts, construct the improved policy:
            pi_improved(a) = softmax(log(prior(a)) + sigma_inv(completedQ(a)))
        where sigma_inv is the logit transform for values in [-1, 1]:
            sigma_inv(q) = atanh(q) = 0.5 * log((1+q)/(1-q))
        and completedQ(a) = Q(a) if visited, else root network value.
        """
        action_dim = self.adapter.spec.action_dim
        legal_mask = root.legal_mask
        legal = np.flatnonzero(legal_mask > 0)
        policy = np.zeros((action_dim,), dtype=np.float32)

        if legal.size == 0:
            return policy

        if root.terminal or not root.edges:
            if legal.size > 0:
                policy[legal] = 1.0 / float(legal.size)
            return policy

        # Reconstruct priors from root (stored as edge.prior after normalization)
        priors = np.zeros((action_dim,), dtype=np.float32)
        for action, edge in root.edges.items():
            priors[int(action)] = float(edge.prior)
        prior_total = float(priors.sum())
        if prior_total <= 0:
            priors[legal] = 1.0 / float(legal.size)

        # Compute completedQ: Q(a) for visited actions, else root value
        root_value = float(root.network_value_root)
        completed_q = np.full((action_dim,), root_value, dtype=np.float32)
        for action, edge in root.edges.items():
            if edge.visit_count > 0:
                completed_q[int(action)] = float(edge.q_root)

        # Improved policy logits: log(prior) + atanh(completedQ)
        # Clamp Q to avoid atanh divergence at ±1
        cq_clamped = np.clip(completed_q[legal], -0.999, 0.999)
        log_prior = np.log(np.clip(priors[legal], 1e-8, None))
        sigma_inv_q = np.arctanh(cq_clamped)
        logits = log_prior + sigma_inv_q

        # Softmax over legal actions
        logits -= float(np.max(logits))  # numerical stability
        exp_logits = np.exp(logits)
        total = float(exp_logits.sum())
        if total <= 0:
            policy[legal] = 1.0 / float(legal.size)
        else:
            policy[legal] = exp_logits / total

        return policy

    def _choose_action(self, policy: np.ndarray, phase: float, *, mode: str) -> int:
        legal = np.flatnonzero(policy > 0)
        if legal.size == 0:
            return 0
        if mode == "eval":
            return int(np.argmax(policy))
        if phase < 0.15:
            temperature = 1.0
        elif phase < 0.35:
            temperature = 0.5
        else:
            temperature = 0.0
        if temperature <= 0:
            return int(np.argmax(policy))
        scaled = np.power(np.clip(policy, 1e-8, None), 1.0 / temperature)
        scaled_sum = float(scaled.sum())
        if scaled_sum <= 0:
            return int(self.rng.choice(legal))
        scaled /= scaled_sum
        return int(self.rng.choice(np.arange(policy.shape[0]), p=scaled))
