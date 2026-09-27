"""Abstract interface every network adapter must implement.

An `Adapter` is the thing that actually talks to a device/host (RouterOS,
a Linux box, or "the local machine" for generic diagnostics). It has no
knowledge of MCP, capabilities, schemas, or the model — `app.mcp.server`
and `app.capabilities` wrap an `Adapter` to expose it as MCP tools /
registry entries, respectively. This mirrors `app.models.base.ModelProvider`
on purpose: same "small interface, structured result, never raise for
expected failures" shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Adapter(ABC):
    """Abstract base class for all network/device adapters."""

    name: str

    @abstractmethod
    def list_capabilities(self) -> list[str]:
        """Return the capability names this adapter can actually service."""
        raise NotImplementedError

    @abstractmethod
    def invoke(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one capability and return a structured result:

            {"success": True, "data": {...}}
            {"success": False, "error": {"code": ..., "message": ...}}

        Implementations must never raise for expected failure modes
        (connection errors, timeouts, auth failures, malformed responses,
        unsupported capability, etc.) — those become a structured error
        result instead. Must never fabricate data: if the underlying
        device/host can't be reached, this returns an error, not made-up
        output.
        """
        raise NotImplementedError

    def health_check(self) -> bool:
        """Return True if the adapter's target is reachable, False
        otherwise (including "not implemented"). Must not raise."""
        return False
