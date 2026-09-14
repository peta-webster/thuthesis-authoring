#!/usr/bin/env python3
"""Run captured subprocesses with bounded descendant lifetime."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Mapping, Optional, Sequence


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate *process* and its descendants as one group when supported."""

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    else:
        # CREATE_NEW_PROCESS_GROUP keeps the process isolated on Windows, but
        # Python has no portable tree-kill primitive there. Killing the direct
        # process is still safer than leaving it running after a timeout.
        process.kill()


def run_captured(
    command: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    timeout: Optional[int] = None,
    env: Optional[Mapping[str, str]] = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and kill its process group on POSIX if timeout expires."""

    kwargs: dict[str, object] = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    process = subprocess.Popen(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(env) if env is not None else None,
        **kwargs,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            list(command),
            timeout,
            output=stdout,
            stderr=stderr,
        )
    return subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)
