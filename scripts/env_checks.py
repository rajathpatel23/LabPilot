from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


@dataclass
class EnvVarCheck:
    name: str
    required: bool = True
    configured: bool = False
    length: int = 0

    def to_dict(self) -> dict:
        """Serialize the check for JSON reporting."""
        return asdict(self)


def inspect_env_var(name: str, required: bool = True) -> EnvVarCheck:
    """Build a check result for a single environment variable."""
    value = os.getenv(name)
    return EnvVarCheck(
        name=name,
        required=required,
        configured=bool(value),
        length=len(value) if value else 0,
    )


def run_checks(spec: Sequence[tuple[str, bool]] | Iterable[tuple[str, bool]]) -> list[EnvVarCheck]:
    """Evaluate a list of (name, required) env var specs."""
    return [inspect_env_var(name, required) for name, required in spec]


def readiness_flags(
    checks: Sequence[EnvVarCheck],
    readiness_map: dict[str, str],
) -> dict[str, bool]:
    """Derive readiness booleans from a mapping of flag -> env var name."""
    flags: dict[str, bool] = {}
    for flag, env_name in readiness_map.items():
        flags[flag] = any(check.name == env_name and check.configured for check in checks)
    return flags
