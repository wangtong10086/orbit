"""Core execution package."""

__all__ = ["ExecutionService", "JobBundle"]


def __getattr__(name: str):
    if name == "ExecutionService":
        from orbit.core.execution.service import ExecutionService

        return ExecutionService
    if name == "JobBundle":
        from orbit.core.execution.bundle import JobBundle

        return JobBundle
    raise AttributeError(name)
