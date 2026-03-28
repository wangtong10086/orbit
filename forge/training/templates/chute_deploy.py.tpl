"""Auto-generated Chutes deployment for {hf_repo}."""
from chutes.chute import NodeSelector
from chutes.chute.template.sglang import build_sglang_chute

chute = build_sglang_chute(
    username="{chutes_username}",
    readme="{hf_repo}",
    model_name="{hf_repo}",
    image="chutes/sglang:nightly-2025081600",
    concurrency=40,
    revision="{revision}",
    node_selector=NodeSelector(
        gpu_count={gpu_count},
        include=["h200"],
    ),
    scaling_threshold=0.5,
    max_instances=2,
    shutdown_after_seconds=28800,
)
