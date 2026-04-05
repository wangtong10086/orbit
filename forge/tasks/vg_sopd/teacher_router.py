"""Environment-aware teacher routing for VG-SOPD."""

from __future__ import annotations

from forge.tasks.vg_sopd.specs import TeacherEndpointSpec, TeacherPolicySpec


DEFAULT_ENV_ORDER: dict[str, tuple[str, ...]] = {
    "GAME": ("specialized", "white_box", "black_box"),
    "QQR": ("white_box", "black_box", "specialized"),
    "NAVWORLD": ("white_box", "black_box", "specialized"),
    "LIVEWEB": ("white_box", "black_box", "specialized"),
    "MEMORYGYM": ("white_box", "black_box", "specialized"),
    "SWE": ("white_box", "black_box", "specialized"),
    "SWE-INFINITE": ("white_box", "black_box", "specialized"),
}


def _enabled_teachers(policy: TeacherPolicySpec) -> dict[str, TeacherEndpointSpec]:
    return {teacher.name: teacher for teacher in policy.teachers if teacher.enabled}


def route_teacher(policy: TeacherPolicySpec, environment: str) -> TeacherEndpointSpec | None:
    teachers = _enabled_teachers(policy)
    env_policy = policy.env_policies.get(environment)
    if env_policy is not None:
        for name in (env_policy.primary, *env_policy.fallbacks):
            if name and name in teachers:
                return teachers[name]
    preferred_kinds = DEFAULT_ENV_ORDER.get(environment, ("white_box", "black_box", "specialized"))
    for kind in preferred_kinds:
        for teacher in teachers.values():
            if teacher.kind == kind:
                return teacher
    return next(iter(teachers.values()), None)


__all__ = ["DEFAULT_ENV_ORDER", "route_teacher"]
