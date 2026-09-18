from typing import Any

import pytest

from fieldwise.schemas.compiler import SchemaError, compile_schema
from fieldwise.schemas.registry import builtin_names, compile_builtin, load_builtin


def _walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Every object node in a compiled schema."""
    found = []
    if node.get("type") == "object":
        found.append(node)
        for child in node["properties"].values():
            found.extend(_walk(child))
    if node.get("type") == "array":
        found.extend(_walk(node["items"]))
    return found


def test_receipt_is_a_builtin() -> None:
    assert builtin_names() == ["receipt"]


def test_every_object_is_strict_and_every_leaf_is_nullable() -> None:
    compiled = compile_builtin("receipt")
    for obj in _walk(compiled.strict):
        assert obj["additionalProperties"] is False
        assert obj["required"] == list(obj["properties"])
    leaf = compiled.strict["properties"]["total"]
    assert leaf["anyOf"] == [{"type": "number"}, {"type": "null"}]
    assert "final amount" in leaf["description"]


def test_field_paths_and_matchers() -> None:
    compiled = compile_builtin("receipt")
    meta = compiled.field_meta_dict()
    assert meta["total"]["matcher"] == "money"
    assert meta["item_count"]["matcher"] == "integer"
    assert meta["line_items"]["matcher"] == "list"
    assert meta["line_items"]["children"] == [
        "line_items[].name",
        "line_items[].quantity",
        "line_items[].unit_price",
        "line_items[].line_total",
    ]
    assert meta["line_items[].name"]["matcher"] == "text"
    assert "line_items" not in compiled.leaf_paths
    assert "line_items[].line_total" in compiled.leaf_paths


def test_nested_objects_and_scalar_arrays() -> None:
    compiled = compile_schema(
        {
            "title": "invoice",
            "type": "object",
            "properties": {
                "seller": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "vat_id": {"type": "string"}},
                },
                "tags": {"type": "array", "items": {"type": "string"}},
                "paid": {"type": "boolean"},
            },
        }
    )
    paths = [f.path for f in compiled.fields]
    assert paths == ["seller", "seller.name", "seller.vat_id", "tags", "tags[]", "paid"]
    assert compiled.strict["properties"]["tags"]["items"]["anyOf"][0] == {"type": "string"}
    assert compiled.field_meta_dict()["paid"]["matcher"] == "boolean"


@pytest.mark.parametrize(
    "authored",
    [
        {"title": "x", "type": "array", "items": {"type": "string"}},
        {"title": "x", "type": "object", "properties": {"a": {"type": "date"}}},
        {"title": "x", "type": "object", "properties": {"a": {"type": "array"}}},
        {"title": "x", "type": "object", "properties": {"a": {"type": "object"}}},
        {
            "title": "x",
            "type": "object",
            "properties": {"a": {"type": "string", "x-fieldwise": {"matcher": "regex"}}},
        },
    ],
)
def test_unsupported_shapes_are_rejected(authored: dict[str, Any]) -> None:
    with pytest.raises(SchemaError):
        compile_schema(authored)


def test_builtin_receipt_round_trips_through_json() -> None:
    authored = load_builtin("receipt")
    assert authored["title"] == "receipt"
    assert compile_schema(authored).name == "receipt"
