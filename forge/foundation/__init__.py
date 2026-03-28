"""Layer 0 foundation contracts and shared policies.

Keep package import side effects minimal. Concrete exports are resolved lazily
so contract modules can import each other without package-init cycles.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "EnvironmentCatalog",
    "EnvironmentDefinition",
    "ScoringPolicy",
    "ArtifactRef",
    "ArtifactStore",
    "CanonicalRepository",
    "ConversationPacker",
    "EvaluationRunner",
    "EvaluationSpec",
    "ExecutionProvider",
    "TrainingLaunch",
    "IdentityConversationPacker",
    "LocalCanonicalRepository",
    "Qwen3ConversationPacker",
    "TrainingSpec",
    "default_environment_catalog",
    "strict_geo_mean",
]


_EXPORT_MAP = {
    "ArtifactRef": ("forge.foundation.contracts", "ArtifactRef"),
    "ArtifactStore": ("forge.foundation.contracts", "ArtifactStore"),
    "CanonicalRepository": ("forge.foundation.contracts", "CanonicalRepository"),
    "ConversationPacker": ("forge.foundation.contracts", "ConversationPacker"),
    "EvaluationRunner": ("forge.foundation.contracts", "EvaluationRunner"),
    "EvaluationSpec": ("forge.foundation.contracts", "EvaluationSpec"),
    "ExecutionProvider": ("forge.foundation.contracts", "ExecutionProvider"),
    "TrainingLaunch": ("forge.foundation.contracts", "TrainingLaunch"),
    "TrainingSpec": ("forge.foundation.contracts", "TrainingSpec"),
    "EnvironmentCatalog": ("forge.foundation.environment_catalog", "EnvironmentCatalog"),
    "EnvironmentDefinition": ("forge.foundation.environment_catalog", "EnvironmentDefinition"),
    "default_environment_catalog": ("forge.foundation.environment_catalog", "default_environment_catalog"),
    "IdentityConversationPacker": ("forge.foundation.packing", "IdentityConversationPacker"),
    "LocalCanonicalRepository": ("forge.foundation.repository", "LocalCanonicalRepository"),
    "Qwen3ConversationPacker": ("forge.foundation.packing", "Qwen3ConversationPacker"),
    "ScoringPolicy": ("forge.foundation.scoring", "ScoringPolicy"),
    "strict_geo_mean": ("forge.foundation.scoring", "strict_geo_mean"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
