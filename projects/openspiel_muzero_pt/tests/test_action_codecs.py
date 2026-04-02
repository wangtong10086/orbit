from __future__ import annotations

import numpy as np

from projects.openspiel_muzero_pt.games.action_codecs import get_action_codec
from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY


def test_othello_action_roundtrip_and_pass_planes():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    codec = get_action_codec(spec)
    assert codec.encode_dense(17, spec) == 17
    assert codec.decode_dense(17, spec) == 17
    planes = codec.to_action_planes(64, spec)
    assert planes.shape == (3, 8, 8)
    assert float(planes[2].sum().item()) == 64.0


def test_othello_symmetry_remap_rot90():
    spec = DEFAULT_REGISTRY.get_spec(400_000_000)
    codec = get_action_codec(spec)
    action = 0  # a1
    remapped = codec.remap_under_symmetry(action, "rot90", spec)
    assert remapped == 7


def test_clobber_direction_roundtrip_planes():
    spec = DEFAULT_REGISTRY.get_spec(700_000_000)
    codec = get_action_codec(spec)
    action = codec.encode_dense(24, spec)
    planes = codec.to_action_planes(action, spec)
    assert planes.shape == (3, 7, 7)
    assert np.isclose(float(planes[0].sum().item()), 1.0)
    assert np.isclose(float(planes[1].sum().item()), 1.0)
