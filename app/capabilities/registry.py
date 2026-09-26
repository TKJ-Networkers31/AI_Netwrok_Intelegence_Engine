"""The capability registry: ANIE's allowlist of invocable tools.

There is no plugin framework here on purpose (per the Phase 2 scope) — just
a flat, in-memory map from capability name to `CapabilityDefinition`.
Nothing outside this registry can ever be invoked: `CapabilityExecutor`
rejects any capability name it doesn't find here before doing anything
else, so this registry *is* the allowlist, not a separate check layered on
top of one.
"""

from __future__ import annotations

from typing import Optional

from app.capabilities.types import CapabilityDefinition


class DuplicateCapabilityError(Exception):
    """Raised when two capabilities are registered under the same name."""


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}

    def register(self, capability: CapabilityDefinition) -> None:
        if capability.name in self._capabilities:
            raise DuplicateCapabilityError(f"Capability '{capability.name}' is already registered.")
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Optional[CapabilityDefinition]:
        return self._capabilities.get(name)

    def is_registered(self, name: str) -> bool:
        return name in self._capabilities

    def list_all(self) -> list[CapabilityDefinition]:
        return list(self._capabilities.values())

    def list_names(self) -> list[str]:
        return list(self._capabilities.keys())

    def for_server(self, server: str) -> list[CapabilityDefinition]:
        return [cap for cap in self._capabilities.values() if cap.server == server]
