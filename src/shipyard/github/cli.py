"""Authenticated GitHub transport."""

import json
import os
import subprocess


def api(endpoint: str, *, payload: dict[str, str] | None = None) -> object:
    args = ["gh", "api", "--hostname", "github.com", endpoint]
    if payload is not None:
        args.extend(("--input", "-"))
    result = subprocess.run(
        args,
        input=json.dumps(payload).encode() if payload is not None else None,
        capture_output=True,
        check=True,
        timeout=45,
        env={**os.environ, "GH_PROMPT_DISABLED": "1"},
    )
    return json.loads(result.stdout)
