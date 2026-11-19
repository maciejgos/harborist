"""Worker subprocess for one cancellable host-helper request."""

import os
import sys
from http.client import HTTPException
from pathlib import Path

from shipyard.sandbox.host_runtime import MAX_TRANSFER
from shipyard.sandbox.host_transport import Request, request_host


def main() -> int:
    try:
        timeout, limit, *args = sys.argv[1:]
        request = Request(
            args=tuple(args),
            timeout=float(timeout),
            limit=int(limit),
            input_bytes=sys.stdin.buffer.read(MAX_TRANSFER + 1),
        )
        response = request_host(
            os.environ["SHIPYARD_SANDBOX_HOST"],
            int(os.environ["SHIPYARD_SANDBOX_PORT"]),
            Path(os.environ["SHIPYARD_SANDBOX_TOKEN_FILE"]).read_bytes().strip(),
            request,
        )
        sys.stdout.write(response.model_dump_json())
    except HTTPException, KeyError, OSError, ValueError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
