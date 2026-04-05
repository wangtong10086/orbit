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
    "StrictModel": ("orbit.foundation.schema", "StrictModel"),
    "FrozenModel": ("orbit.foundation.schema", "FrozenModel"),
    "VersionedDocument": ("orbit.foundation.schema", "VersionedDocument"),
    "RequestContext": ("orbit.foundation.schema", "RequestContext"),
    "ValidationIssue": ("orbit.foundation.schema", "ValidationIssue"),
    "SchemaErrorResponse": ("orbit.foundation.schema", "SchemaErrorResponse"),
    "ConversationMessage": ("orbit.foundation.data_contracts", "ConversationMessage"),
    "CanonicalEntry": ("orbit.foundation.data_contracts", "CanonicalEntry"),
    "CanonicalSyncReport": ("orbit.foundation.data_contracts", "CanonicalSyncReport"),
    "CollectResult": ("orbit.foundation.data_contracts", "CollectResult"),
    "CollectSyncResult": ("orbit.foundation.data_contracts", "CollectSyncResult"),
    "IngestReport": ("orbit.foundation.data_contracts", "IngestReport"),
    "DatasetBuildReport": ("orbit.foundation.data_contracts", "DatasetBuildReport"),
    "PublishReport": ("orbit.foundation.data_contracts", "PublishReport"),
    "RepoSyncReport": ("orbit.foundation.data_contracts", "RepoSyncReport"),
    "CollectPipelineReport": ("orbit.foundation.data_contracts", "CollectPipelineReport"),
    "AuditEvent": ("orbit.foundation.audit", "AuditEvent"),
    "AuditSnapshot": ("orbit.foundation.audit", "AuditSnapshot"),
    "AuditWriter": ("orbit.foundation.audit", "AuditWriter"),
    "ArtifactRef": ("orbit.foundation.contracts", "ArtifactRef"),
    "ArtifactStore": ("orbit.foundation.contracts", "ArtifactStore"),
    "CanonicalRepository": ("orbit.foundation.contracts", "CanonicalRepository"),
    "ConversationPacker": ("orbit.foundation.contracts", "ConversationPacker"),
    "EvaluationRunner": ("orbit.foundation.contracts", "EvaluationRunner"),
    "EvaluationSpec": ("orbit.foundation.contracts", "EvaluationSpec"),
    "TrainingSpec": ("orbit.foundation.contracts", "TrainingSpec"),
    "EnvironmentCatalog": ("orbit.foundation.environment_catalog", "EnvironmentCatalog"),
    "EnvironmentDefinition": ("orbit.foundation.environment_catalog", "EnvironmentDefinition"),
    "default_environment_catalog": ("orbit.foundation.environment_catalog", "default_environment_catalog"),
    "ScriptEvaluationRunner": ("orbit.foundation.evaluation", "ScriptEvaluationRunner"),
    "IdentityConversationPacker": ("orbit.foundation.packing", "IdentityConversationPacker"),
    "LocalCanonicalRepository": ("orbit.foundation.repository", "LocalCanonicalRepository"),
    "Qwen3ConversationPacker": ("orbit.foundation.packing", "Qwen3ConversationPacker"),
    "ScoringPolicy": ("orbit.foundation.scoring", "ScoringPolicy"),
    "strict_geo_mean": ("orbit.foundation.scoring", "strict_geo_mean"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(name)
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    return getattr(module, attr_name)
