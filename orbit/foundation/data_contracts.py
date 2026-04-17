"""Pydantic-first data collection and canonical data contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue, TypeAdapter, ValidationError, field_validator, model_validator

from orbit.foundation.schema import FrozenModel, StrictModel, ValidationIssue


class ConversationMessage(StrictModel):
    """Framework-level message schema for collected conversations."""

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
        str_strip_whitespace=False,
        arbitrary_types_allowed=True,
        use_enum_values=False,
    )

    role: str
    content: str = ""
    tool_calls: JsonValue | None = None
    tool_call_id: str | None = None
    tools: JsonValue | None = None

    @field_validator("content", mode="before")
    @classmethod
    def _normalize_content(cls, value):
        if value is None:
            return ""
        return str(value)


class CanonicalEntryBase(StrictModel):
    """Base canonical data record shared by all collect environments."""

    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
        str_strip_whitespace=False,
        arbitrary_types_allowed=True,
        use_enum_values=False,
    )

    env: str
    messages: list[ConversationMessage] = Field(min_length=2)
    score: float
    source: str = ""


class GameCanonicalEntry(CanonicalEntryBase):
    env: Literal["GAME"] = "GAME"
    game: str | None = None
    seed: int | None = None


class NavworldCanonicalEntry(CanonicalEntryBase):
    env: Literal["NAVWORLD"] = "NAVWORLD"
    distill_model: str | None = None
    task_id: int | None = None
    problem_type: str | None = None
    seed: int | None = None


class LivewebCanonicalEntry(CanonicalEntryBase):
    env: Literal["LIVEWEB"] = "LIVEWEB"
    distill_model: str | None = None
    seed: int | None = None
    num_subtasks: int | None = None


class MemorygymCanonicalEntry(CanonicalEntryBase):
    env: Literal["MEMORYGYM"] = "MEMORYGYM"
    template: str | None = None
    seed: int | None = None
    event_type: str | None = None
    event_idx: int | None = None
    total_events: int | None = None
    strategy: str | None = None
    tier_config: JsonValue | None = None
    correct: int | None = None
    total: int | None = None


class SweCanonicalEntry(CanonicalEntryBase):
    env: Literal["SWE-INFINITE"] = "SWE-INFINITE"
    instance_id: str | None = None
    base_instance_id: str | None = None
    repo: str | None = None
    language: str | None = None
    format: str | None = None


class LgcCanonicalEntry(CanonicalEntryBase):
    env: Literal["LGC-v2"] = "LGC-v2"


class PrintCanonicalEntry(CanonicalEntryBase):
    env: Literal["PRINT"] = "PRINT"


CanonicalEntry = Annotated[
    GameCanonicalEntry
    | NavworldCanonicalEntry
    | LivewebCanonicalEntry
    | MemorygymCanonicalEntry
    | SweCanonicalEntry
    | LgcCanonicalEntry
    | PrintCanonicalEntry,
    Field(discriminator="env"),
]


CANONICAL_ENTRY_ADAPTER = TypeAdapter(CanonicalEntry)


class CollectedRawArtifact(FrozenModel):
    status: str = "success"
    file: str = ""
    reason: str = ""


class CollectSyncResult(FrozenModel):
    status: str = ""
    env: str = ""
    path: str = ""
    repo_id: str = ""
    reason: str = ""


class CollectResult(FrozenModel):
    output: str = ""
    staging_path: str = ""
    raw_path: str = ""
    records: int = 0
    success: int = 0
    filtered: int = 0
    failed: int = 0
    errors: int = 0
    trajectories: int = 0
    samples: int = 0
    distribution: dict[str, int] = Field(default_factory=dict)
    target_per_game: int = 0
    per_game: dict[str, int] = Field(default_factory=dict)
    generators: dict[str, str] = Field(default_factory=dict)
    generator_source: str = ""
    mode: str = ""
    new_count: int = 0
    skipped_dup: int = 0
    skipped_invalid: int = 0
    total: int = 0
    blocked_reason: str = ""
    raw_files: list[str] = Field(default_factory=list)
    reason: str = ""


class IngestDetail(FrozenModel):
    kind: str
    message: str


class IngestReport(FrozenModel):
    status: str = "success"
    appended: int = 0
    would_append: int = 0
    dropped: int = 0
    invalid: int = 0
    duplicates_skipped: int = 0
    previous_count: int = 0
    new_total: int = 0
    reason: str = ""
    issues: list[tuple[int, list[str]]] = Field(default_factory=list)
    details: list[IngestDetail] = Field(default_factory=list)
    hf_upload: CollectedRawArtifact | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, raw):
        if not isinstance(raw, dict):
            return raw
        raw = dict(raw)
        if "accepted" in raw and "appended" not in raw:
            raw["appended"] = raw.pop("accepted")
        if "duplicate" in raw and "duplicates_skipped" not in raw:
            raw["duplicates_skipped"] = raw.pop("duplicate")
        return raw

    @property
    def total(self) -> int:
        return self.appended + self.dropped + self.invalid + self.duplicates_skipped

    @property
    def accepted(self) -> int:
        return self.appended

    @property
    def duplicate(self) -> int:
        return self.duplicates_skipped

    def summary(self) -> str:
        return (
            f"Ingested: {self.appended}/{self.total} "
            f"(dropped={self.dropped}, invalid={self.invalid}, dup={self.duplicates_skipped})"
        )


class PublishReport(FrozenModel):
    status: str = "success"
    repo_id: str = ""
    config: str = "mixed"
    split: str = "train"
    rows: int = 0
    parquet_path: str = ""
    dataset_card: CollectedRawArtifact | None = None
    reason: str = ""


class RepoSyncReport(FrozenModel):
    status: str = "success"
    repo_id: str = ""
    downloaded: list[str] = Field(default_factory=list)
    reason: str = ""


class CanonicalSyncReport(FrozenModel):
    status: str = "success"
    env: str = ""
    path: str = ""
    repo_id: str = ""
    reason: str = ""


class DatasetBuildReport(FrozenModel):
    output_path: str
    total: int = 0
    by_env: dict[str, int] = Field(default_factory=dict)


class CollectPipelineReport(FrozenModel):
    status: str = "success"
    repo_id: str = ""
    env: str = ""
    source: str = ""
    sync: list[CollectSyncResult] = Field(default_factory=list)
    collect: CollectResult = Field(default_factory=CollectResult)
    raw_uploads: list[CollectedRawArtifact] = Field(default_factory=list)
    ingest: IngestReport = Field(default_factory=IngestReport)
    mixed: PublishReport = Field(default_factory=PublishReport)


class MemorygymRawRequest(FrozenModel):
    output: str
    seeds: int = 10
    templates: tuple[str, ...] = ()
    tier: str = "lite"
    tier_mix: bool = False
    jobs: int = 1


class SweSyncRequest(FrozenModel):
    machine: str = ""
    dry_run: bool = False
    upload: bool = True
    repo_id: str = ""
    remote_dir: str = ""


SweFormat = Literal["miniswe", "codex"]
SweAttemptStatus = Literal["success", "verify_fail", "quality_fail", "infra_fail", "no_patch"]


class SweAttemptManifestV1(FrozenModel):
    schema_version: Literal["swe_attempt.v1"] = "swe_attempt.v1"
    attempt_id: str
    instance_id: str
    format: SweFormat
    status: SweAttemptStatus
    canonical_path: str = ""
    raw_log_path: str = ""
    messages_path: str = ""
    verify_passed: bool = False
    hints_applied: int = 0
    assistant_turns: int = 0
    changed_files: tuple[str, ...] = ()
    detail: str = ""


class SweCollectionRunManifestV1(FrozenModel):
    schema_version: Literal["swe_collection_run.v1"] = "swe_collection_run.v1"
    run_id: str
    collector_profile: str
    format: SweFormat
    output_dir: str
    canonical_path: str
    attempts_path: str
    log_dir: str
    task_source: str = ""
    task_count: int = 0
    successful_attempts: int = 0
    failed_attempts: int = 0
    remote_sync_dir: str = ""


SweTerminalStatus = Literal["success", "verify_fail", "quality_fail", "no_patch", "infra_fail", "max_steps"]
SweFailureKind = Literal["no_patch", "wrong_patch", "verify_fail", "terminal_test_regression", "tool_error"]
SweBucketKind = Literal["A", "B", "C", "V"]


class SweIssueOracleV1(FrozenModel):
    schema_version: Literal["swe_issue_oracle.v1"] = "swe_issue_oracle.v1"
    base_instance_id: str
    touched_files: tuple[str, ...] = ()
    touched_symbols: tuple[str, ...] = ()
    edit_type: str = "unknown"
    related_tests: tuple[str, ...] = ()
    patch_size_lower: int = 0
    patch_size_upper: int = 0
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SweIssueRubricV1(FrozenModel):
    schema_version: Literal["swe_issue_rubric.v1"] = "swe_issue_rubric.v1"
    rubric_id: str
    base_instance_id: str
    likely_modules: tuple[str, ...] = ()
    required_constraints: tuple[str, ...] = ()
    common_pseudo_solutions: tuple[str, ...] = ()
    forbidden_patterns: tuple[str, ...] = ()
    raw_response: str = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SweLocalizationCandidateV1(FrozenModel):
    schema_version: Literal["swe_localization_candidate.v1"] = "swe_localization_candidate.v1"
    candidate_id: str
    base_instance_id: str
    format: SweFormat
    temperature: float = 0.0
    candidate_files: tuple[str, ...] = ()
    candidate_symbols: tuple[str, ...] = ()
    hypothesis: str = ""
    edit_type: str = "unknown"
    oracle_scores: dict[str, float] = Field(default_factory=dict)
    rubric_score: float = 0.0
    total_score: float = 0.0
    raw_response: str = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SwePatchPlanV1(FrozenModel):
    schema_version: Literal["swe_patch_plan.v1"] = "swe_patch_plan.v1"
    plan_id: str
    base_instance_id: str
    format: SweFormat
    localization_id: str = ""
    target_files: tuple[str, ...] = ()
    target_symbols: tuple[str, ...] = ()
    plan_steps: tuple[str, ...] = ()
    diff_sketch: str = ""
    edit_type: str = "unknown"
    oracle_scores: dict[str, float] = Field(default_factory=dict)
    rubric_score: float = 0.0
    total_score: float = 0.0
    raw_response: str = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SweStepStateV1(FrozenModel):
    schema_version: Literal["swe_step_state.v1"] = "swe_step_state.v1"
    state_id: str
    trajectory_id: str
    instance_id: str
    base_instance_id: str = ""
    format: SweFormat
    step_index: int
    tool_name: str = "shell"
    command: str = ""
    submit: bool = False
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    git_status_short: str = ""
    changed_files: tuple[str, ...] = ()
    diff_excerpt: str = ""


class SweRawTrajectoryV1(FrozenModel):
    schema_version: Literal["swe_raw_trajectory.v1"] = "swe_raw_trajectory.v1"
    trajectory_id: str
    run_id: str
    instance_id: str
    base_instance_id: str = ""
    repo: str = ""
    language: str = ""
    format: SweFormat
    sampling_temperature: float = 0.0
    student_model: str = ""
    student_endpoint: str = ""
    collector: str = ""
    teacher_calls: int = 0
    repair_round: int = 0
    rubric_score: float = 0.0
    oracle_scores: dict[str, float] = Field(default_factory=dict)
    localization_id: str = ""
    plan_id: str = ""
    messages: tuple[ConversationMessage, ...] = ()
    state_paths: tuple[str, ...] = ()
    final_patch: str = ""
    terminal_status: SweTerminalStatus = "max_steps"
    terminal_detail: str = ""
    verify_passed: bool = False
    terminal_output: str = ""
    assistant_turns: int = 0
    changed_files: tuple[str, ...] = ()
    rubric_enabled: bool = False
    rubric_degraded_reason: str = ""
    task_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    raw_log_path: str = ""


class SweFailurePointV1(FrozenModel):
    schema_version: Literal["swe_failure_point.v1"] = "swe_failure_point.v1"
    failure_id: str
    trajectory_id: str
    instance_id: str
    base_instance_id: str = ""
    format: SweFormat
    step_index: int = 0
    failure_kind: SweFailureKind
    localization_evidence: str = ""
    offline_hints_used: tuple[str, ...] = ()
    state_path: str = ""


class SweCritiqueRecordV1(FrozenModel):
    schema_version: Literal["swe_critique_record.v1"] = "swe_critique_record.v1"
    critique_id: str
    trajectory_id: str
    failure_id: str
    instance_id: str
    base_instance_id: str = ""
    format: SweFormat
    teacher_model: str = ""
    teacher_endpoint: str = ""
    repair_round: int = 1
    near_miss: bool = False
    rubric_score: float = 0.0
    oracle_scores: dict[str, float] = Field(default_factory=dict)
    localization_id: str = ""
    plan_id: str = ""
    critique: str = ""
    revised_action: str = ""
    raw_response: str = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SweBucketSampleV1(FrozenModel):
    schema_version: Literal["swe_bucket_sample.v1"] = "swe_bucket_sample.v1"
    sample_id: str
    bucket: SweBucketKind
    instance_id: str
    base_instance_id: str = ""
    trajectory_id: str = ""
    failure_id: str = ""
    critique_id: str = ""
    env: Literal["SWE-INFINITE"] = "SWE-INFINITE"
    format: SweFormat
    messages: tuple[ConversationMessage, ...] = ()
    source: str = ""
    terminal_success: bool = False
    first_error_index: int = -1
    process_weights: tuple[float, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SweCollectionRunManifestV2(FrozenModel):
    schema_version: Literal["swe_collection_run.v2"] = "swe_collection_run.v2"
    run_id: str
    format: SweFormat | Literal["mixed"] = "mixed"
    output_dir: str
    task_source: str = ""
    student_model: str = ""
    student_endpoint: str = ""
    teacher_model: str = ""
    teacher_endpoint: str = ""
    student_probe_status: str = ""
    teacher_probe_status: str = ""
    docker_probe_status: str = ""
    rubric_enabled: bool = False
    rubric_degraded_reason: str = ""
    raw_dir: str = ""
    states_dir: str = ""
    relabel_dir: str = ""
    bucket_dir: str = ""
    canonical_path: str = ""
    verifier_dataset_path: str = ""
    log_dir: str = ""
    stage_counts: dict[str, int] = Field(default_factory=dict)
    notes: dict[str, JsonValue] = Field(default_factory=dict)


def _issue(loc: tuple[str, ...], msg: str, kind: str = "value_error") -> ValidationIssue:
    return ValidationIssue(loc=loc, msg=msg, kind=kind)


def _validation_issues_from_error(exc: ValidationError) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            loc=tuple(str(part) for part in err.get("loc", ())),
            msg=err.get("msg", "validation error"),
            kind=err.get("type", "value_error"),
        )
        for err in exc.errors()
    ]


def validate_canonical_entry(entry: dict, *, env_spec, expected_env: str | None = None) -> tuple[CanonicalEntryBase | None, list[ValidationIssue]]:
    """Validate one canonical entry against Pydantic schema and env policy."""

    try:
        model = CANONICAL_ENTRY_ADAPTER.validate_python(entry)
    except ValidationError as exc:
        return None, _validation_issues_from_error(exc)

    issues: list[ValidationIssue] = []
    if expected_env and model.env != expected_env:
        issues.append(_issue(("env",), f"env='{model.env}' expected '{expected_env}'"))

    valid_roles = getattr(env_spec, "valid_roles", {"system", "user", "assistant"})
    allowed_extra = getattr(env_spec, "allowed_extra_fields", set())
    terminal_roles = getattr(env_spec, "terminal_roles", {"assistant"})

    for index, msg in enumerate(model.messages):
        if msg.role not in valid_roles:
            issues.append(_issue(("messages", str(index), "role"), f"role='{msg.role}' not in {valid_roles}"))
        for field_name in ("tool_calls", "tool_call_id", "tools"):
            if getattr(msg, field_name) is not None and field_name not in allowed_extra:
                issues.append(_issue(("messages", str(index), field_name), f"field '{field_name}' not allowed for env {model.env}"))
        for extra_key in (msg.model_extra or {}).keys():
            if extra_key not in allowed_extra:
                issues.append(_issue(("messages", str(index), extra_key), f"extra field '{extra_key}' not allowed for env {model.env}"))

    if model.messages and model.messages[-1].role not in terminal_roles:
        allowed = "/".join(sorted(terminal_roles))
        issues.append(_issue(("messages", str(len(model.messages) - 1), "role"), f"last msg role='{model.messages[-1].role}' (must be {allowed})"))

    return model, issues
