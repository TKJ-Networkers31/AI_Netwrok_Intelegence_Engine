from __future__ import annotations

import pytest

from app.capabilities.registry import CapabilityRegistry, DuplicateCapabilityError
from app.capabilities.types import CapabilityDefinition, RiskLevel


def make_capability(name="ping", server="generic", risk_level=RiskLevel.READ_ONLY) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=name,
        description="test capability",
        server=server,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object"},
        risk_level=risk_level,
    )


def test_register_and_get():
    registry = CapabilityRegistry()
    capability = make_capability()

    registry.register(capability)

    assert registry.get("ping") is capability
    assert registry.is_registered("ping") is True
    assert registry.is_registered("missing") is False


def test_get_missing_returns_none():
    registry = CapabilityRegistry()

    assert registry.get("missing") is None


def test_duplicate_registration_raises():
    registry = CapabilityRegistry()
    registry.register(make_capability())

    with pytest.raises(DuplicateCapabilityError):
        registry.register(make_capability())


def test_list_all_and_list_names():
    registry = CapabilityRegistry()
    registry.register(make_capability(name="ping"))
    registry.register(make_capability(name="traceroute"))

    assert sorted(registry.list_names()) == ["ping", "traceroute"]
    assert len(registry.list_all()) == 2


def test_for_server_filters_by_server():
    registry = CapabilityRegistry()
    registry.register(make_capability(name="mikrotik_get_interfaces", server="mikrotik"))
    registry.register(make_capability(name="ping", server="generic"))

    mikrotik_caps = registry.for_server("mikrotik")

    assert [c.name for c in mikrotik_caps] == ["mikrotik_get_interfaces"]
