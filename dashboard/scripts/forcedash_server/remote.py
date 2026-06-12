"""SSH helpers for running bounded Python snippets on the log/config host."""

import subprocess

from forcedash_server.config import (
    CONNECT_TIMEOUT_SECONDS,
    REMOTE_COMMAND_TIMEOUT_SECONDS,
    SSH_HOST,
)


def run_remote_python(
    script: str,
    *,
    input_text: str | None = None,
    timeout: int = REMOTE_COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command = [
        "ssh",
        "-o",
        f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
        SSH_HOST,
        f"python3 - <<'PY'\n{script}\nPY",
    ]
    return subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
