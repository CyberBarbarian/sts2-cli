"""Shared JSON-lines transport for the interactive and full-run CLI drivers."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from typing import Any


def build_runtime_env(
    *,
    local_dotnet: str,
    local_dotnet_dir: str,
    lib_dir: str,
    force_local_lib: bool,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Bind a child process to repository-local runtime dependencies."""
    env = dict(os.environ if base is None else base)
    if os.path.isfile(local_dotnet):
        env["DOTNET_ROOT"] = local_dotnet_dir
        env["PATH"] = local_dotnet_dir + os.pathsep + env.get("PATH", "")
    if force_local_lib:
        env["STS2_LIB"] = lib_dir
        env["STS2_GAME_DIR"] = lib_dir
    else:
        env.setdefault("STS2_LIB", lib_dir)
        env.setdefault("STS2_GAME_DIR", lib_dir)
    return env


class HeadlessSession:
    """Own one headless subprocess and its line-delimited JSON transport."""

    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str],
        stderr: int | None,
        eof_error: str | None,
        on_action: Callable[[dict[str, Any]], None] | None = None,
        on_state: Callable[[dict[str, Any]], None] | None = None,
        on_skip: Callable[[str], None] | None = None,
    ) -> None:
        self._eof_error = eof_error
        self._on_action = on_action
        self._on_state = on_state
        self._on_skip = on_skip
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )

    def read(self) -> dict[str, Any] | None:
        """Read the next JSON object, ignoring diagnostic stdout lines."""
        assert self.process.stdout is not None
        while True:
            line = self.process.stdout.readline().strip()
            if not line:
                if self._eof_error is not None:
                    raise RuntimeError(self._eof_error)
                return None
            if not line.startswith("{"):
                if self._on_skip is not None:
                    self._on_skip(line)
                continue
            response = json.loads(line)
            if self._on_state is not None:
                self._on_state(response)
            return response

    def send(
        self,
        command: dict[str, Any],
        *,
        record: bool = True,
    ) -> dict[str, Any] | None:
        if record and self._on_action is not None:
            self._on_action(command)
        self.write(command)
        return self.read()

    def write(
        self,
        command: dict[str, Any],
        *,
        record_action: bool = False,
    ) -> None:
        if record_action and self._on_action is not None:
            self._on_action(command)
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except Exception:
            self.process.kill()
            self.process.wait(timeout=5)
        finally:
            for stream in (
                self.process.stdin,
                self.process.stdout,
                self.process.stderr,
            ):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
