from __future__ import annotations

from app.adapters.generic import GenericAdapter
from app.capabilities.definitions import build_default_registry
from app.mcp.adapter_handler import AdapterToolHandler


def test_list_tools_only_includes_capabilities_the_adapter_supports():
    adapter = GenericAdapter()
    registry = build_default_registry()
    handler = AdapterToolHandler(adapter, registry.for_server("generic"))

    names = {tool.name for tool in handler.list_tools()}

    assert names == {"ping", "traceroute", "dns_lookup", "tcp_connectivity"}


def test_invoke_delegates_to_adapter():
    adapter = GenericAdapter()
    registry = build_default_registry()
    handler = AdapterToolHandler(adapter, registry.for_server("generic"))

    result = handler.invoke("dns_lookup", {"host": "not-a-valid-host!!"})

    # Whatever the adapter returns (here: an error, since the host is
    # invalid) should be passed straight through.
    assert result["success"] is False


def test_invoke_unknown_tool_never_reaches_adapter():
    adapter = GenericAdapter()
    registry = build_default_registry()
    handler = AdapterToolHandler(adapter, registry.for_server("generic"))

    result = handler.invoke("mikrotik_get_interfaces", {})

    assert result["success"] is False
    assert result["error"]["code"] == "unknown_tool"
