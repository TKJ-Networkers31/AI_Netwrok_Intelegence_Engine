from __future__ import annotations

from app.adapters.linux import LinuxAdapter


def test_list_capabilities_are_namespaced():
    adapter = LinuxAdapter()

    capabilities = adapter.list_capabilities()

    assert "linux_get_interfaces" in capabilities
    assert all(c.startswith("linux_") for c in capabilities)


def test_every_capability_returns_not_implemented_without_fabricating_data():
    adapter = LinuxAdapter()

    for capability in adapter.list_capabilities():
        result = adapter.invoke(capability, {})
        assert result["success"] is False
        assert result["error"]["code"] == "not_implemented"
        assert "data" not in result


def test_unsupported_capability():
    adapter = LinuxAdapter()

    result = adapter.invoke("linux_reboot", {})

    assert result["success"] is False
    assert result["error"]["code"] == "unsupported_capability"


def test_health_check_false():
    adapter = LinuxAdapter()

    assert adapter.health_check() is False
