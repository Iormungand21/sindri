#!/usr/bin/env python3
"""Generate TypeScript types from Pydantic event schemas.

This script generates TypeScript interfaces from the Pydantic models
defined in sindri/core/event_schemas.py.

Usage:
    python scripts/generate_typescript_types.py

Output:
    sindri/web/static/src/types/events.generated.ts
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sindri.core.event_schemas import API_VERSION, EVENT_PAYLOAD_MODELS


def json_schema_to_ts_type(schema: dict[str, Any] | bool, indent: int = 0) -> str:
    """Convert JSON Schema type to TypeScript type."""

    # Handle boolean schema (true = any, false = never)
    if isinstance(schema, bool):
        return "unknown" if schema else "never"

    # Handle $ref (references to other schemas)
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return ref_name

    # Handle anyOf (union types, typically Optional)
    if "anyOf" in schema:
        types = []
        for sub_schema in schema["anyOf"]:
            if sub_schema.get("type") == "null":
                types.append("null")
            else:
                types.append(json_schema_to_ts_type(sub_schema, indent))
        return " | ".join(types)

    # Handle allOf (intersection types)
    if "allOf" in schema:
        types = [json_schema_to_ts_type(s, indent) for s in schema["allOf"]]
        return " & ".join(types)

    schema_type = schema.get("type")

    # Handle enum
    if "enum" in schema:
        return " | ".join(f'"{v}"' for v in schema["enum"])

    # Handle basic types
    if schema_type == "string":
        return "string"
    elif schema_type == "integer" or schema_type == "number":
        return "number"
    elif schema_type == "boolean":
        return "boolean"
    elif schema_type == "null":
        return "null"
    elif schema_type == "array":
        items_type = json_schema_to_ts_type(schema.get("items", {}), indent)
        return f"{items_type}[]"
    elif schema_type == "object":
        additional_props = schema.get("additionalProperties")
        if additional_props is not None and additional_props is not False:
            if isinstance(additional_props, bool):
                return "Record<string, unknown>"
            value_type = json_schema_to_ts_type(additional_props, indent)
            return f"Record<string, {value_type}>"
        elif "properties" in schema:
            return generate_inline_interface(schema, indent)
        return "Record<string, unknown>"

    # Default fallback
    return "unknown"


def generate_inline_interface(schema: dict[str, Any], indent: int = 0) -> str:
    """Generate inline TypeScript interface for an object schema."""
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not props:
        return "Record<string, unknown>"

    lines = ["{"]
    for prop_name, prop_schema in props.items():
        ts_type = json_schema_to_ts_type(prop_schema, indent + 1)
        optional = "" if prop_name in required else "?"
        description = prop_schema.get("description", "")
        if description:
            lines.append(f"  /** {description} */")
        lines.append(f"  {prop_name}{optional}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def pydantic_to_typescript_interface(model_class: type, name: str) -> str:
    """Convert a Pydantic model to a TypeScript interface."""
    schema = model_class.model_json_schema()

    lines = []

    # Add JSDoc comment
    if model_class.__doc__:
        lines.append(f"/** {model_class.__doc__.strip()} */")

    lines.append(f"export interface {name} {{")

    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    for prop_name, prop_schema in props.items():
        ts_type = json_schema_to_ts_type(prop_schema)
        optional = "" if prop_name in required else "?"
        description = prop_schema.get("description", "")
        if description:
            lines.append(f"  /** {description} */")
        lines.append(f"  {prop_name}{optional}: {ts_type};")

    lines.append("}")
    return "\n".join(lines)


def generate_typescript_types() -> str:
    """Generate complete TypeScript types file."""
    output_lines = [
        "/**",
        " * Auto-generated TypeScript types for Sindri WebSocket events.",
        f" * API Version: {API_VERSION}",
        " *",
        " * DO NOT EDIT MANUALLY - regenerate with:",
        " *   python scripts/generate_typescript_types.py",
        " */",
        "",
    ]

    # Generate interface for each event type
    output_lines.append("// === Event Payload Interfaces ===")
    output_lines.append("")

    for event_type, model_class in EVENT_PAYLOAD_MODELS.items():
        interface_name = f"{event_type}Data"
        interface_code = pydantic_to_typescript_interface(model_class, interface_name)
        output_lines.append(interface_code)
        output_lines.append("")

    # Generate EventType union
    output_lines.append("// === Event Type Union ===")
    output_lines.append("")
    event_types = list(EVENT_PAYLOAD_MODELS.keys())
    output_lines.append("export type EventType =")
    for i, event_type in enumerate(event_types):
        separator = ";" if i == len(event_types) - 1 else ""
        output_lines.append(f"  | '{event_type}'{separator}")
    output_lines.append("")

    # Generate EventTypeDataMap for type-safe event handling
    output_lines.append("// === Event Type to Data Type Map ===")
    output_lines.append("")
    output_lines.append("export interface EventTypeDataMap {")
    for event_type in event_types:
        output_lines.append(f"  {event_type}: {event_type}Data;")
    output_lines.append("}")
    output_lines.append("")

    # Generate typed WebSocket event discriminated union
    output_lines.append("// === Typed WebSocket Event (Discriminated Union) ===")
    output_lines.append("")
    output_lines.append("export type TypedWebSocketEvent =")
    for i, event_type in enumerate(event_types):
        separator = ";" if i == len(event_types) - 1 else ""
        output_lines.append(
            f"  | {{ type: '{event_type}'; data: {event_type}Data; timestamp: number; task_id?: string | null }}{separator}"
        )
    output_lines.append("")

    # Generate helper type guard function signatures
    output_lines.append("// === Type Guard Helpers ===")
    output_lines.append("")
    output_lines.append(
        "export function isEventType<T extends EventType>(event: TypedWebSocketEvent, type: T): event is TypedWebSocketEvent & { type: T; data: EventTypeDataMap[T] } {"
    )
    output_lines.append("  return event.type === type;")
    output_lines.append("}")
    output_lines.append("")

    # Generate list of all event types
    output_lines.append("// === All Event Types ===")
    output_lines.append("")
    output_lines.append("export const ALL_EVENT_TYPES: EventType[] = [")
    for event_type in event_types:
        output_lines.append(f"  '{event_type}',")
    output_lines.append("];")
    output_lines.append("")

    # Add API version constant
    output_lines.append("// === API Version ===")
    output_lines.append("")
    output_lines.append(f"export const API_VERSION = '{API_VERSION}';")
    output_lines.append("")

    return "\n".join(output_lines)


def main():
    """Generate TypeScript types and write to file."""
    output_path = project_root / "sindri" / "web" / "static" / "src" / "types" / "events.generated.ts"

    types_content = generate_typescript_types()

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(types_content)
    print(f"Generated TypeScript types at: {output_path}")
    print(f"API Version: {API_VERSION}")
    print(f"Event types: {len(EVENT_PAYLOAD_MODELS)}")


if __name__ == "__main__":
    main()
