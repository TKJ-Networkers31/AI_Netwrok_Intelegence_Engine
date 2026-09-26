"""Minimal, dependency-free schema validation for tool call arguments.

Deliberately NOT a full JSON Schema implementation (no nested/array-item
validation, no formats, no $ref) — just enough to catch the obvious "model
forgot a required field" / "model passed a string instead of an int" cases
without adding a `jsonschema` dependency, matching the "minimal
dependencies" constraint in the Phase 2 brief.
"""

from __future__ import annotations

from typing import Any

_TYPE_MAP: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    if not isinstance(arguments, dict):
        return [f"arguments must be an object, got {type(arguments).__name__}"]

    errors: list[str] = []
    properties: dict[str, Any] = schema.get("properties", {}) or {}
    required: list[str] = schema.get("required", []) or []
    allow_additional = schema.get("additionalProperties", True)

    for field_name in required:
        if field_name not in arguments:
            errors.append(f"missing required field: '{field_name}'")

    for key, value in arguments.items():
        if key not in properties:
            if not allow_additional:
                errors.append(f"unexpected field: '{key}'")
            continue
        expected_type = properties[key].get("type")
        if expected_type and not _type_matches(value, expected_type):
            errors.append(
                f"field '{key}' expected type '{expected_type}', got {type(value).__name__}"
            )

    return errors


def _type_matches(value: Any, expected_type: str) -> bool:
    py_type = _TYPE_MAP.get(expected_type)
    if py_type is None:
        return True  # unknown/unenforced type keyword: don't block on it
    if isinstance(value, bool):
        # bool is a subclass of int in Python; don't let it silently
        # satisfy "integer"/"number".
        return expected_type == "boolean"
    return isinstance(value, py_type)
