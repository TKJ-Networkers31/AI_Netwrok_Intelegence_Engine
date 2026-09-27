"""Types describing a single ANIE "capability" — a model-invocable, tool-
shaped operation (e.g. `mikrotik_get_interfaces`, `ping`) that is backed by
an adapter behind an MCP server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """How much trust a capability requires before it may execute.

    Phase 2 registers only `READ_ONLY` capabilities, and
    `CapabilityExecutor` refuses to execute anything else — this is the
    "read-only by default" boundary from the spec, encoded as data rather
    than a scattered set of `if` checks.
    """

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    description: str
    server: str  # which MCP server (by config name) provides this capability
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    permissions: tuple[str, ...] = ()
