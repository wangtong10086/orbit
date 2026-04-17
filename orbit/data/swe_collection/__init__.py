"""Staged SWE collection subsystem for autonomous sampling and offline relabeling."""

from .buckets import SweBucketBuilder, run_swe_build_buckets, run_swe_train_verifier_dataset
from .collector import SweAutonomousSampler, parse_sampling_temps, run_swe_sampling
from .exporter import SweCollectionExporter
from .judge import SweTerminalVerifier, VerificationOutcome
from .relabel import SweFailureRelabeler, run_swe_relabel
from .runtime import SweDockerWorkspace, SweDockerWorkspaceRuntime
from .sessions import CodexStudentSession, FailureCritiqueSession, MiniSweStudentSession, StudentTurn
from .smoke import run_swe_smoke
from .task_source import SweTaskSource

__all__ = [
    "CodexStudentSession",
    "FailureCritiqueSession",
    "MiniSweStudentSession",
    "StudentTurn",
    "SweAutonomousSampler",
    "SweBucketBuilder",
    "SweCollectionExporter",
    "SweDockerWorkspace",
    "SweDockerWorkspaceRuntime",
    "SweFailureRelabeler",
    "SweTaskSource",
    "SweTerminalVerifier",
    "VerificationOutcome",
    "parse_sampling_temps",
    "run_swe_build_buckets",
    "run_swe_relabel",
    "run_swe_sampling",
    "run_swe_smoke",
    "run_swe_train_verifier_dataset",
]
