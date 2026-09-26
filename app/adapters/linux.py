"""Placeholder Linux adapter.

Per the Phase 2 brief, MikroTik is the one target that needs a real,
working, end-to-end adapter; Linux capabilities only need to be registered
so the model/registry surface reflects the intended final shape. Every
invocation here returns a structured `not_implemented` error — it never
fabricates process/interface/log data, per the "never fabricate results"
requirement.

A real implementation would likely talk to the local host directly (no
remote transport needed) or over SSH to a remote host; either is future
work and deliberately out of scope here.
"""

from __future__ import annotations

from typing import Any

from app.adapters.base import Adapter

_CAPABILITIES = [
    "linux_get_interfaces",
    "linux_get_routes",
    "linux_get_neighbors",
    "linux_get_processes",
    "linux_get_cpu",
    "linux_get_memory",
    "linux_get_disk",
    "linux_get_services",
    "linux_get_logs",
    "linux_get_dns",
]


class LinuxAdapter(Adapter):
    name = "linux"

    def list_capabilities(self) -> list[str]:
        return list(_CAPABILITIES)

    def invoke(self, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if capability not in _CAPABILITIES:
            return {
                "success": False,
                "error": {
                    "code": "unsupported_capability",
                    "message": f"Linux adapter does not support '{capability}'.",
                },
            }
        return {
            "success": False,
            "error": {
                "code": "not_implemented",
                "message": f"The Linux adapter does not yet implement '{capability}' (Phase 2 placeholder).",
            },
        }

    def health_check(self) -> bool:
        return False
