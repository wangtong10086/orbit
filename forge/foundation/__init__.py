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
    "StrictModel",
    "FrozenModel",
    "VersionedDocument",
    "RequestContext",
    "ValidationIssue",
    "SchemaErrorResponse",
    "ConversationMessage",
    "CanonicalEntry",
    "CanonicalSyncReport",
    "CollectResult",
    "CollectSyncResult",
    "IngestReport",
    "DatasetBuildReport",
    "PublishReport",
    "RepoSyncReport",
    "CollectPipelineReport",
    "AuditEvent",
    "AuditSnapshot",
    "AuditWriter",
    "ArtifactRef",
    "ArtifactStore",
    "CanonicalRepository",
    "ConversationPacker",
    "EvaluationRunner",
    "EvaluationSpec",
    "ScriptEvaluationRunner",
    "IdentityConversationPacker",
    "LocalCanonicalRepository",
    "Qwen3ConversationPacker",
    "TrainingSpec",
    "default_environment_catalog",
    "strict_geo_mean",
]


_EXPORT_MAP = {
    "StrictModel": ("forge.foundation.schema", "StrictModel"),
    "FrozenModel": ("forge.foundation.schema", "FrozenModel"),
    "VersionedDocument": ("forge.foundation.schema", "VersionedDocument"),
    "RequestContext": ("forge.foundation.schema", "RequestContext"),
    "ValidationIssue": ("forge.foundation.schema", "ValidationIssue"),
    "SchemaErrorResponse": ("forge.foundation.schema", "SchemaErrorResponse"),
    "ConversationMessage": ("forge.foundation.data_contracts", "ConversationMessage"),
    "CanonicalEntry": ("forge.foundation.data_contracts", "CanonicalEntry"),
    "CanonicalSyncReport": ("forge.foundation.data_contracts", "CanonicalSyncReport"),
    "CollectResult": ("forge.foundation.data_contracts", "CollectResult"),
    "CollectSyncResult": ("forge.foundation.data_contracts", "CollectSyncResult"),
    "IngestReport": ("forge.foundation.data_contracts", "IngestReport"),
    "DatasetBuildReport": ("forge.foundation.data_contracts", "DatasetBuildReport"),
    "PublishReport": ("forge.foundation.data_contracts", "PublishReport"),
    "RepoSyncReport": ("forge.foundation.data_contracts", "RepoSyncReport"),
    "CollectPipelineReport": ("forge.foundation.data_contracts", "CollectPipelineReport"),
    "AuditEvent": ("forge.foundation.audit", "AuditEvent"),
    "AuditSnapshot": ("forge.foundation.audit", "AuditSnapshot"),
    "AuditWriter": ("forge.foundation.audit", "AuditWriter"),
    "ArtifactRef": ("forge.foundation.contracts", "ArtifactRef"),
    "ArtifactStore": ("forge.foundation.contracts", "ArtifactStore"),
    "CanonicalRepository": ("forge.foundation.contracts", "CanonicalRepository"),
    "ConversationPacker": ("forge.foundation.contracts", "ConversationPacker"),
    "EvaluationRunner": ("forge.foundation.contracts", "EvaluationRunner"),
    "EvaluationSpec": ("forge.foundation.contracts", "EvaluationSpec"),
    "TrainingSpec": ("forge.foundation.contracts", "TrainingSpec"),
    "EnvironmentCatalog": ("forge.foundation.environment_catalog", "EnvironmentCatalog"),
    "EnvironmentDefinition": ("forge.foundation.environment_catalog", "EnvironmentDefinition"),
    "default_environment_catalog": ("forge.foundation.environment_catalog", "default_environment_catalog"),
    "ScriptEvaluationRunner": ("forge.foundation.evaluation", "ScriptEvaluationRunner"),
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
