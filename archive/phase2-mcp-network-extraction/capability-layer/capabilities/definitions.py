"""The default Phase 2 capability set.

Capability names are namespaced by target ("mikrotik_"/"linux_") wherever
the spec's per-vendor lists would otherwise collide (e.g. both MikroTik and
Linux list a `get_interfaces`/`get_routes`/`get_dns`/`get_logs`) — a flat
registry (and a model's `tools` list) needs globally unique names. Generic,
target-agnostic diagnostics (`ping`, `traceroute`, `dns_lookup`,
`tcp_connectivity`) are not namespaced since they don't collide with
anything.

Every capability here is `RiskLevel.READ_ONLY`: Phase 2 only implements
read-only network visibility/diagnostics, so nothing else is registered,
and `CapabilityExecutor` would refuse to execute it even if it were.
"""

from __future__ import annotations

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import CapabilityDefinition, RiskLevel

_EMPTY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}

_HOST_ONLY_SCHEMA = {
    "type": "object",
    "properties": {"host": {"type": "string", "description": "Target hostname or IP address."}},
    "required": ["host"],
    "additionalProperties": False,
}

_PING_SCHEMA = {
    "type": "object",
    "properties": {
        "host": {"type": "string", "description": "Target hostname or IP address."},
        "count": {"type": "integer", "description": "Number of echo requests to send (default 4)."},
    },
    "required": ["host"],
    "additionalProperties": False,
}

_TRACEROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "host": {"type": "string", "description": "Target hostname or IP address."},
        "max_hops": {"type": "integer", "description": "Maximum number of hops (default 30)."},
    },
    "required": ["host"],
    "additionalProperties": False,
}

_TCP_CONNECTIVITY_SCHEMA = {
    "type": "object",
    "properties": {
        "host": {"type": "string", "description": "Target hostname or IP address."},
        "port": {"type": "integer", "description": "TCP port to test."},
    },
    "required": ["host", "port"],
    "additionalProperties": False,
}


def _no_arg_capability(name: str, description: str, server: str) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        description=description,
        server=server,
        input_schema=_EMPTY_INPUT_SCHEMA,
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_ONLY,
        permissions=("network.read",),
    )


_MIKROTIK_CAPABILITIES = [
    _no_arg_capability(
        "mikrotik_get_interfaces", "List network interfaces on a MikroTik/RouterOS device.", "mikrotik"
    ),
    _no_arg_capability(
        "mikrotik_get_ip_addresses",
        "List configured IP addresses on a MikroTik/RouterOS device.",
        "mikrotik",
    ),
    _no_arg_capability(
        "mikrotik_get_routes", "List the IPv4 routing table of a MikroTik/RouterOS device.", "mikrotik"
    ),
    _no_arg_capability(
        "mikrotik_get_arp", "List ARP table entries on a MikroTik/RouterOS device.", "mikrotik"
    ),
    _no_arg_capability(
        "mikrotik_get_system_resources",
        "Get CPU/memory/uptime resource usage of a MikroTik/RouterOS device.",
        "mikrotik",
    ),
    _no_arg_capability(
        "mikrotik_get_logs", "Read recent log entries from a MikroTik/RouterOS device.", "mikrotik"
    ),
    _no_arg_capability(
        "mikrotik_get_dns", "Get DNS configuration of a MikroTik/RouterOS device.", "mikrotik"
    ),
    _no_arg_capability(
        "mikrotik_get_dhcp", "List DHCP server leases on a MikroTik/RouterOS device.", "mikrotik"
    ),
    _no_arg_capability(
        "mikrotik_get_firewall", "List firewall filter rules on a MikroTik/RouterOS device.", "mikrotik"
    ),
]

# Linux capabilities are registered so the model/registry surface is
# complete, but `LinuxAdapter` is a placeholder (see app/adapters/linux.py)
# — every invocation returns a structured `not_implemented` error rather
# than fabricating data, per the "never fabricate results" requirement.
_LINUX_CAPABILITIES = [
    _no_arg_capability(
        "linux_get_interfaces", "List network interfaces on a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_routes", "List the routing table of a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_neighbors",
        "List neighbor/ARP table entries on a Linux host. (Not yet implemented.)",
        "linux",
    ),
    _no_arg_capability(
        "linux_get_processes", "List running processes on a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_cpu", "Get CPU usage of a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_memory", "Get memory usage of a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_disk", "Get disk usage of a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_services", "List running services on a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_logs", "Read recent system logs on a Linux host. (Not yet implemented.)", "linux"
    ),
    _no_arg_capability(
        "linux_get_dns", "Get DNS configuration of a Linux host. (Not yet implemented.)", "linux"
    ),
]

_GENERIC_CAPABILITIES = [
    CapabilityDefinition(
        name="ping",
        description="ICMP ping a host to check basic reachability.",
        server="generic",
        input_schema=_PING_SCHEMA,
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_ONLY,
        permissions=("network.probe",),
    ),
    CapabilityDefinition(
        name="traceroute",
        description="Trace the network path to a host.",
        server="generic",
        input_schema=_TRACEROUTE_SCHEMA,
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_ONLY,
        permissions=("network.probe",),
    ),
    CapabilityDefinition(
        name="dns_lookup",
        description="Resolve a hostname to its IP address(es).",
        server="generic",
        input_schema=_HOST_ONLY_SCHEMA,
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_ONLY,
        permissions=("network.read",),
    ),
    CapabilityDefinition(
        name="tcp_connectivity",
        description="Check whether a TCP port on a host is reachable.",
        server="generic",
        input_schema=_TCP_CONNECTIVITY_SCHEMA,
        output_schema={"type": "object"},
        risk_level=RiskLevel.READ_ONLY,
        permissions=("network.probe",),
    ),
]


def build_default_registry() -> CapabilityRegistry:
    """Build the full Phase 2 capability registry.

    This registers every capability ANIE *knows about*, whether or not a
    live MCP server is currently connected for it — "no server connected"
    is a runtime concern handled by `CapabilityExecutor` (a
    `server_unavailable` error), not a registration-time concern.
    """
    registry = CapabilityRegistry()
    for capability in (*_MIKROTIK_CAPABILITIES, *_LINUX_CAPABILITIES, *_GENERIC_CAPABILITIES):
        registry.register(capability)
    return registry
