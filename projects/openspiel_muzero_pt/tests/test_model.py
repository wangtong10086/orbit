from __future__ import annotations

import torch

from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY
from projects.openspiel_muzero_pt.model.board_muzero import BoardMuZeroConfig, BoardMuZeroNet
from projects.openspiel_muzero_pt.games.action_codecs import get_action_codec


def test_othello_initial_and_recurrent_inference_shapes():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    net = BoardMuZeroNet(
        BoardMuZeroConfig(
            input_channels=spec.input_channels,
            board_height=spec.pad_h,
            board_width=spec.pad_w,
            action_dim=spec.action_dim,
            channels=64,
            repr_blocks=2,
            dyn_blocks=1,
            head_hidden=128,
        )
    )
    obs = torch.randn(3, spec.input_channels, spec.pad_h, spec.pad_w)
    initial = net.initial_inference(obs)
    assert initial.latent.shape == (3, 64, 8, 8)
    assert initial.policy_logits.shape == (3, spec.action_dim)
    assert initial.value.shape == (3,)

    codec = get_action_codec(spec)
    action_planes = torch.cat([codec.to_action_planes(action, spec).unsqueeze(0) for action in [19, 26, 64]], dim=0)
    recurrent = net.recurrent_inference(initial.latent, action_planes)
    assert recurrent.latent.shape == (3, 64, 8, 8)
    assert recurrent.policy_logits.shape == (3, spec.action_dim)
    assert recurrent.value.shape == (3,)
    assert recurrent.reward.shape == (3,)
