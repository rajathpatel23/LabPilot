from __future__ import annotations

import json
import os


def status_row(name: str, required: bool = True) -> dict:
    val = os.getenv(name)
    return {
        "name": name,
        "required": required,
        "configured": bool(val),
        "length": len(val) if val else 0,
    }


def main() -> None:
    checks = [
        status_row("NEBIUS_API_KEY", required=False),
        status_row("NEBIUS_API_BASE", required=False),
        status_row("NEBIUS_MODEL", required=False),
        status_row("TAVILY_API_KEY", required=False),
    ]

    summary = {
        "ready_for_nebius_llm": any(c["name"] == "NEBIUS_API_KEY" and c["configured"] for c in checks),
        "ready_for_tavily": any(c["name"] == "TAVILY_API_KEY" and c["configured"] for c in checks),
        "checks": checks,
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

