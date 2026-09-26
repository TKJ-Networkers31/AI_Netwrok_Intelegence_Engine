"""Transport abstraction for the MCP client.

Only a stdio (subprocess) transport is implemented in Phase 2, but
`app.mcp.client.MCPClient` only ever depends on this `Transport` interface
— it has no idea whether the other end is a subprocess, a socket, or (as in
the test suite) an in-memory fake. Additional transports can be added later
without touching the client, the capability layer, or any vendor code.
"""

from __future__ import annotations

import json
import select
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Optional


class Transport(ABC):
    """A bidirectional, message-oriented channel to an MCP server."""

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection. Must raise on failure."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection. Must be safe to call more than once,
        and safe to call even if `connect()` was never called or failed."""

    @abstractmethod
    def send(self, message: dict[str, Any]) -> None:
        """Send one message. Must raise on failure (e.g. broken pipe)."""

    @abstractmethod
    def receive(self, timeout: float) -> Optional[dict[str, Any]]:
        """Block for at most `timeout` seconds for the next message.

        Returns the message, or `None` if the peer cleanly closed the
        connection. Raises `TimeoutError` if nothing arrives in time.
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Best-effort liveness check; not authoritative (a `send`/
        `receive` can still fail even if this returns True)."""


class StdioTransport(Transport):
    """Launches `command` as a subprocess and speaks newline-delimited JSON
    over its stdin/stdout — the exact framing `app.mcp.server.MCPServer`
    expects on the other end.
    """

    def __init__(
        self,
        command: str,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
    ):
        self._command = command
        self._args = list(args or [])
        self._env = env
        self._process: Optional[subprocess.Popen] = None

    def connect(self) -> None:
        self._process = subprocess.Popen(
            [self._command, *self._args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=self._env,
        )

    def disconnect(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            process.kill()

    def send(self, message: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise ConnectionError("StdioTransport is not connected.")
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def receive(self, timeout: float) -> Optional[dict[str, Any]]:
        if self._process is None or self._process.stdout is None:
            raise ConnectionError("StdioTransport is not connected.")
        ready, _, _ = select.select([self._process.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError(f"No response from '{self._command}' within {timeout}s")
        line = self._process.stdout.readline()
        if line == "":
            return None  # the process closed its stdout
        return json.loads(line)

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.poll() is None
