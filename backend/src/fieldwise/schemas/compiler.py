"""Turns an authored JSON Schema into (a) the strict schema Claude's structured outputs require and
(b) flat per-field metadata the eval matchers and the UI work from.

Authoring rules (a small JSON Schema subset):
- objects with `properties`; arrays of objects or of scalars; scalars string/number/integer/boolean
- every leaf is optional to the author and *nullable* to the model — "not printed" is a first-class
  answer, so the strict schema wraps each leaf in `anyOf: [<type>, null]`
- `x-fieldwise: {"matcher": "money" | "integer" | "text" | "date"}` overrides the matcher derived
  from the type (number → money, integer → integer, string → text, boolean → boolean)
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

Matcher = Literal["text", "money", "number", "integer", "boolean", "date", "list", "object"]

SCALAR_TYPES = {"string", "number", "integer", "boolean"}
DEFAULT_MATCHERS: dict[str, Matcher] = {
    "string": "text",
    "number": "money",
    "integer": "integer",
    "boolean": "boolean",
}


class SchemaError(ValueError):
    """The authored schema uses something outside the supported subset."""


@dataclass(frozen=True)
class FieldMeta:
    """One addressable field. Paths use `[]` for array items, e.g. `line_items[].name`."""

    path: str
    type: str
    matcher: Matcher
    description: str = ""
    children: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "type": self.type,
            "matcher": self.matcher,
            "description": self.description,
            "children": list(self.children),
        }


@dataclass(frozen=True)
class CompiledSchema:
    name: str
    strict: dict[str, Any]
    fields: tuple[FieldMeta, ...]

    @property
    def leaf_paths(self) -> tuple[str, ...]:
        return tuple(f.path for f in self.fields if f.matcher not in ("list", "object"))

    def field_meta_dict(self) -> dict[str, Any]:
        return {f.path: f.to_dict() for f in self.fields}


def compile_schema(authored: dict[str, Any]) -> CompiledSchema:
    name = str(authored.get("title") or "schema")
    if authored.get("type") != "object" or not isinstance(authored.get("properties"), dict):
        raise SchemaError("the root must be an object with properties")
    fields: list[FieldMeta] = []
    strict = _compile_object(authored, prefix="", fields=fields)
    return CompiledSchema(name=name, strict=strict, fields=tuple(fields))


def _compile_object(node: dict[str, Any], prefix: str, fields: list[FieldMeta]) -> dict[str, Any]:
    properties: dict[str, Any] = node["properties"]
    out_props: dict[str, Any] = {}
    for key, child in properties.items():
        path = f"{prefix}{key}"
        out_props[key] = _compile_node(child, path=path, fields=fields)
    result: dict[str, Any] = {
        "type": "object",
        "properties": out_props,
        "required": list(out_props),
        "additionalProperties": False,
    }
    if node.get("description"):
        result["description"] = node["description"]
    return result


def _compile_node(node: dict[str, Any], path: str, fields: list[FieldMeta]) -> dict[str, Any]:
    node_type = node.get("type")
    description = str(node.get("description", ""))
    if node_type == "object":
        if not isinstance(node.get("properties"), dict):
            raise SchemaError(f"{path}: objects need properties")
        fields.append(
            FieldMeta(
                path=path,
                type="object",
                matcher="object",
                description=description,
                children=tuple(f"{path}.{k}" for k in node["properties"]),
            )
        )
        return _compile_object(node, prefix=f"{path}.", fields=fields)
    if node_type == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            raise SchemaError(f"{path}: arrays need items")
        item_path = f"{path}[]"
        children: tuple[str, ...] = ()
        if items.get("type") == "object":
            children = tuple(f"{item_path}.{k}" for k in items.get("properties", {}))
        fields.append(
            FieldMeta(
                path=path, type="array", matcher="list", description=description, children=children
            )
        )
        compiled_items = (
            _compile_object(items, prefix=f"{item_path}.", fields=fields)
            if items.get("type") == "object"
            else _compile_node(items, path=item_path, fields=fields)
        )
        result: dict[str, Any] = {"type": "array", "items": compiled_items}
        if description:
            result["description"] = description
        return result
    if node_type in SCALAR_TYPES:
        matcher = _matcher_for(node, path)
        fields.append(
            FieldMeta(path=path, type=node_type, matcher=matcher, description=description)
        )
        leaf: dict[str, Any] = {"type": node_type}
        for key in ("enum", "format", "minimum", "maximum"):
            if key in node:
                leaf[key] = deepcopy(node[key])
        nullable: dict[str, Any] = {"anyOf": [leaf, {"type": "null"}]}
        if description:
            nullable["description"] = description
        return nullable
    raise SchemaError(f"{path}: unsupported type {node_type!r}")


def _matcher_for(node: dict[str, Any], path: str) -> Matcher:
    override = node.get("x-fieldwise", {}).get("matcher")
    if override is None:
        return DEFAULT_MATCHERS[str(node["type"])]
    if override not in ("text", "money", "number", "integer", "boolean", "date"):
        raise SchemaError(f"{path}: unknown matcher {override!r}")
    return override  # type: ignore[no-any-return]
