from __future__ import annotations

from pathlib import Path

from projects.openspiel_muzero_pt.games.affine_registry import DEFAULT_REGISTRY


def test_every_registered_variant_has_a_base_config():
    config_dir = Path(__file__).resolve().parents[1] / "configs"
    missing = []
    for spec in DEFAULT_REGISTRY:
        config_path = config_dir / f"{spec.variant_name}.yaml"
        if not config_path.exists():
            missing.append(spec.variant_name)
    assert not missing, f"Missing configs for variants: {missing}"
