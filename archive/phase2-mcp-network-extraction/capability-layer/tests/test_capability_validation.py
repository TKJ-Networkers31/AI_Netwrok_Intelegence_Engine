from __future__ import annotations

from app.capabilities.validation import validate_arguments

SCHEMA = {
    "type": "object",
    "properties": {
        "host": {"type": "string"},
        "count": {"type": "integer"},
        "enabled": {"type": "boolean"},
    },
    "required": ["host"],
    "additionalProperties": False,
}


def test_valid_arguments_pass():
    errors = validate_arguments(SCHEMA, {"host": "10.0.0.1", "count": 4})

    assert errors == []


def test_missing_required_field():
    errors = validate_arguments(SCHEMA, {"count": 4})

    assert any("host" in e for e in errors)


def test_wrong_type_reported():
    errors = validate_arguments(SCHEMA, {"host": "10.0.0.1", "count": "not-a-number"})

    assert any("count" in e for e in errors)


def test_bool_does_not_satisfy_integer():
    errors = validate_arguments(SCHEMA, {"host": "10.0.0.1", "count": True})

    assert any("count" in e for e in errors)


def test_unexpected_field_rejected_when_additional_properties_false():
    errors = validate_arguments(SCHEMA, {"host": "10.0.0.1", "extra": "nope"})

    assert any("extra" in e for e in errors)


def test_unexpected_field_allowed_when_additional_properties_true():
    permissive_schema = dict(SCHEMA)
    permissive_schema["additionalProperties"] = True

    errors = validate_arguments(permissive_schema, {"host": "10.0.0.1", "extra": "fine"})

    assert errors == []


def test_arguments_must_be_a_dict():
    errors = validate_arguments(SCHEMA, ["not", "a", "dict"])  # type: ignore[arg-type]

    assert len(errors) == 1
    assert "object" in errors[0]


def test_empty_schema_accepts_anything():
    errors = validate_arguments({}, {"anything": 123})

    assert errors == []
