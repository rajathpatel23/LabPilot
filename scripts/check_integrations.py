from __future__ import annotations

import json
from typing import Sequence

try:  # pragma: no cover - runtime import shim for script/module execution
    from .env_checks import EnvVarCheck, readiness_flags, run_checks
except ImportError:  # pragma: no cover
    from env_checks import EnvVarCheck, readiness_flags, run_checks

ENV_VARS_TO_CHECK: Sequence[tuple[str, bool]] = (
    ("NEBIUS_API_KEY", False),
    ("NEBIUS_API_BASE", False),
    ("NEBIUS_MODEL", False),
    ("TAVILY_API_KEY", False),
)

READINESS_MAP: dict[str, str] = {
    "ready_for_nebius_llm": "NEBIUS_API_KEY",
    "ready_for_tavily": "TAVILY_API_KEY",
}


def serialize_checks(checks: Sequence[EnvVarCheck]) -> list[dict]:
    return [check.to_dict() for check in checks]


def main() -> None:
    checks = run_checks(ENV_VARS_TO_CHECK)
    summary = {
        **readiness_flags(checks, READINESS_MAP),
        "checks": serialize_checks(checks),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
