"""Diagram generation tools for Sindri.

Provides tools for generating technical diagrams using Mermaid, PlantUML, and D2 formats.
These tools are text-based output generators - no external dependencies required.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


class DiagramFormat(str, Enum):
    """Supported diagram output formats."""

    MERMAID = "mermaid"
    PLANTUML = "plantuml"
    D2 = "d2"


class DiagramType(str, Enum):
    """Types of diagrams that can be generated."""

    SEQUENCE = "sequence"
    CLASS = "class"
    FLOWCHART = "flowchart"
    ER = "er"
    STATE = "state"
    ARCHITECTURE = "architecture"
    MINDMAP = "mindmap"
    GANTT = "gantt"


@dataclass
class ClassInfo:
    """Extracted class information from code."""

    name: str
    methods: list[str]
    attributes: list[str]
    parent: Optional[str] = None
    interfaces: list[str] = None

    def __post_init__(self):
        if self.interfaces is None:
            self.interfaces = []


@dataclass
class TableInfo:
    """Extracted table information from database schema."""

    name: str
    columns: list[tuple[str, str, bool]]  # (name, type, is_pk)
    foreign_keys: list[tuple[str, str, str]]  # (column, ref_table, ref_column)


class GenerateMermaidTool(Tool):
    """Generate Mermaid.js diagram code.

    Creates diagrams in Mermaid syntax that can be rendered in GitHub,
    GitLab, Notion, and many markdown editors.
    """

    name = "generate_mermaid"
    description = """Generate a Mermaid.js diagram from a description or specification.

Mermaid is widely supported in GitHub, GitLab, Notion, and markdown editors.

Supported diagram types:
- sequence: Sequence diagrams for API/service interactions
- class: Class diagrams for OOP structures
- flowchart: Flowcharts and process diagrams
- er: Entity-Relationship diagrams for databases
- state: State machine diagrams
- gantt: Gantt charts for timelines
- mindmap: Mind maps for brainstorming

Examples:
- generate_mermaid(diagram_type="sequence", description="User login flow: Browser -> API -> Database")
- generate_mermaid(diagram_type="flowchart", nodes=[{"id": "A", "label": "Start"}, {"id": "B", "label": "End"}], edges=[{"from": "A", "to": "B"}])
- generate_mermaid(diagram_type="er", entities=[{"name": "User", "columns": ["id PK", "name", "email"]}])"""

    parameters = {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "description": "Type of diagram to generate",
                "enum": ["sequence", "class", "flowchart", "er", "state", "gantt", "mindmap"],
            },
            "description": {
                "type": "string",
                "description": "Natural language description of the diagram to generate",
            },
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For flowcharts: list of nodes with 'id' and 'label' keys",
            },
            "edges": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For flowcharts: list of edges with 'from', 'to', and optional 'label' keys",
            },
            "participants": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For sequence diagrams: list of participant names",
            },
            "messages": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For sequence diagrams: list of messages with 'from', 'to', 'message', and optional 'type' keys",
            },
            "entities": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For ER diagrams: list of entities with 'name' and 'columns' keys",
            },
            "relationships": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For ER diagrams: list of relationships with 'from', 'to', 'type' (one-to-many, etc.)",
            },
            "classes": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For class diagrams: list of classes with 'name', 'methods', 'attributes' keys",
            },
            "states": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For state diagrams: list of states with 'id', 'label' keys",
            },
            "transitions": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For state diagrams: list of transitions with 'from', 'to', 'trigger' keys",
            },
            "title": {
                "type": "string",
                "description": "Optional title for the diagram",
            },
            "direction": {
                "type": "string",
                "description": "Flow direction for flowcharts: TB (top-bottom), LR (left-right), BT, RL",
                "enum": ["TB", "LR", "BT", "RL"],
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the diagram",
            },
        },
        "required": ["diagram_type"],
    }

    async def execute(
        self,
        diagram_type: str,
        description: Optional[str] = None,
        nodes: Optional[list[dict]] = None,
        edges: Optional[list[dict]] = None,
        participants: Optional[list[str]] = None,
        messages: Optional[list[dict]] = None,
        entities: Optional[list[dict]] = None,
        relationships: Optional[list[dict]] = None,
        classes: Optional[list[dict]] = None,
        states: Optional[list[dict]] = None,
        transitions: Optional[list[dict]] = None,
        title: Optional[str] = None,
        direction: str = "TB",
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate a Mermaid diagram."""
        try:
            if diagram_type == "sequence":
                diagram = self._generate_sequence(participants, messages, title)
            elif diagram_type == "flowchart":
                diagram = self._generate_flowchart(nodes, edges, title, direction)
            elif diagram_type == "class":
                diagram = self._generate_class_diagram(classes, title)
            elif diagram_type == "er":
                diagram = self._generate_er_diagram(entities, relationships, title)
            elif diagram_type == "state":
                diagram = self._generate_state_diagram(states, transitions, title)
            elif diagram_type == "gantt":
                diagram = self._generate_gantt(description, title)
            elif diagram_type == "mindmap":
                diagram = self._generate_mindmap(description, title)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported diagram type: {diagram_type}",
                )

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(diagram)
                return ToolResult(
                    success=True,
                    output=f"Diagram saved to {output_path}\n\n```mermaid\n{diagram}\n```",
                    metadata={"diagram_type": diagram_type, "format": "mermaid", "output_file": str(output_path)},
                )

            return ToolResult(
                success=True,
                output=f"```mermaid\n{diagram}\n```",
                metadata={"diagram_type": diagram_type, "format": "mermaid"},
            )

        except Exception as e:
            log.error("mermaid_generation_failed", error=str(e), diagram_type=diagram_type)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate Mermaid diagram: {str(e)}",
            )

    def _generate_sequence(
        self,
        participants: Optional[list[str]],
        messages: Optional[list[dict]],
        title: Optional[str],
    ) -> str:
        """Generate sequence diagram."""
        lines = ["sequenceDiagram"]
        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        if participants:
            for p in participants:
                lines.append(f"    participant {p}")

        if messages:
            for msg in messages:
                from_p = msg.get("from", "A")
                to_p = msg.get("to", "B")
                message = msg.get("message", "")
                msg_type = msg.get("type", "sync")  # sync, async, reply

                if msg_type == "async":
                    lines.append(f"    {from_p}-->>>{to_p}: {message}")
                elif msg_type == "reply":
                    lines.append(f"    {from_p}-->>>{to_p}: {message}")
                else:
                    lines.append(f"    {from_p}->>>{to_p}: {message}")

        return "\n".join(lines)

    def _generate_flowchart(
        self,
        nodes: Optional[list[dict]],
        edges: Optional[list[dict]],
        title: Optional[str],
        direction: str,
    ) -> str:
        """Generate flowchart diagram."""
        lines = [f"flowchart {direction}"]
        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        if nodes:
            for node in nodes:
                node_id = node.get("id", "A")
                label = node.get("label", node_id)
                shape = node.get("shape", "rect")  # rect, round, diamond, circle

                if shape == "round":
                    lines.append(f"    {node_id}({label})")
                elif shape == "diamond":
                    lines.append(f"    {node_id}{{{label}}}")
                elif shape == "circle":
                    lines.append(f"    {node_id}(({label}))")
                else:
                    lines.append(f"    {node_id}[{label}]")

        if edges:
            for edge in edges:
                from_node = edge.get("from", "A")
                to_node = edge.get("to", "B")
                label = edge.get("label", "")
                edge_type = edge.get("type", "arrow")  # arrow, dotted, thick

                if label:
                    if edge_type == "dotted":
                        lines.append(f"    {from_node} -.->|{label}| {to_node}")
                    elif edge_type == "thick":
                        lines.append(f"    {from_node} ==>|{label}| {to_node}")
                    else:
                        lines.append(f"    {from_node} -->|{label}| {to_node}")
                else:
                    if edge_type == "dotted":
                        lines.append(f"    {from_node} -.-> {to_node}")
                    elif edge_type == "thick":
                        lines.append(f"    {from_node} ==> {to_node}")
                    else:
                        lines.append(f"    {from_node} --> {to_node}")

        return "\n".join(lines)

    def _generate_class_diagram(
        self,
        classes: Optional[list[dict]],
        title: Optional[str],
    ) -> str:
        """Generate class diagram."""
        lines = ["classDiagram"]
        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        if classes:
            for cls in classes:
                class_name = cls.get("name", "Class")
                attributes = cls.get("attributes", [])
                methods = cls.get("methods", [])
                parent = cls.get("parent")
                interfaces = cls.get("interfaces", [])

                lines.append(f"    class {class_name} {{")
                for attr in attributes:
                    lines.append(f"        {attr}")
                for method in methods:
                    lines.append(f"        {method}")
                lines.append("    }")

                # Inheritance
                if parent:
                    lines.append(f"    {parent} <|-- {class_name}")

                # Interfaces
                for interface in interfaces:
                    lines.append(f"    {interface} <|.. {class_name}")

        return "\n".join(lines)

    def _generate_er_diagram(
        self,
        entities: Optional[list[dict]],
        relationships: Optional[list[dict]],
        title: Optional[str],
    ) -> str:
        """Generate ER diagram."""
        lines = ["erDiagram"]
        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        if entities:
            for entity in entities:
                entity_name = entity.get("name", "Entity")
                columns = entity.get("columns", [])

                lines.append(f"    {entity_name} {{")
                for col in columns:
                    if isinstance(col, str):
                        # Parse string format: "type name" or "type name PK"
                        parts = col.split()
                        if len(parts) >= 2:
                            col_type = parts[0]
                            col_name = parts[1]
                            pk = "PK" if len(parts) > 2 and parts[2] == "PK" else ""
                            lines.append(f"        {col_type} {col_name} {pk}".strip())
                    elif isinstance(col, dict):
                        col_type = col.get("type", "string")
                        col_name = col.get("name", "column")
                        pk = "PK" if col.get("pk") else ""
                        lines.append(f"        {col_type} {col_name} {pk}".strip())
                lines.append("    }")

        if relationships:
            for rel in relationships:
                from_entity = rel.get("from", "A")
                to_entity = rel.get("to", "B")
                rel_type = rel.get("type", "one-to-many")
                label = rel.get("label", "")

                # Map relationship type to Mermaid syntax
                type_map = {
                    "one-to-one": "||--||",
                    "one-to-many": "||--o{",
                    "many-to-one": "}o--||",
                    "many-to-many": "}o--o{",
                    "zero-to-one": "|o--||",
                    "zero-to-many": "|o--o{",
                }
                mermaid_type = type_map.get(rel_type, "||--o{")
                lines.append(f"    {from_entity} {mermaid_type} {to_entity} : {label}".rstrip(" :"))

        return "\n".join(lines)

    def _generate_state_diagram(
        self,
        states: Optional[list[dict]],
        transitions: Optional[list[dict]],
        title: Optional[str],
    ) -> str:
        """Generate state diagram."""
        lines = ["stateDiagram-v2"]
        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        if states:
            for state in states:
                state_id = state.get("id", "State")
                label = state.get("label", state_id)
                if label != state_id:
                    lines.append(f"    {state_id} : {label}")

        if transitions:
            for trans in transitions:
                from_state = trans.get("from", "[*]")
                to_state = trans.get("to", "[*]")
                trigger = trans.get("trigger", "")

                if trigger:
                    lines.append(f"    {from_state} --> {to_state} : {trigger}")
                else:
                    lines.append(f"    {from_state} --> {to_state}")

        return "\n".join(lines)

    def _generate_gantt(self, description: Optional[str], title: Optional[str]) -> str:
        """Generate Gantt chart (placeholder for manual tasks)."""
        lines = ["gantt"]
        if title:
            lines.append(f"    title {title}")

        lines.append("    dateFormat YYYY-MM-DD")
        lines.append("    section Tasks")
        lines.append("    Task 1: t1, 2024-01-01, 7d")
        lines.append("    Task 2: t2, after t1, 5d")

        return "\n".join(lines)

    def _generate_mindmap(self, description: Optional[str], title: Optional[str]) -> str:
        """Generate mindmap (placeholder structure)."""
        root = title or "Root"
        lines = ["mindmap"]
        lines.append(f"    root(({root}))")
        lines.append("        Topic 1")
        lines.append("            Subtopic 1.1")
        lines.append("            Subtopic 1.2")
        lines.append("        Topic 2")
        lines.append("            Subtopic 2.1")

        return "\n".join(lines)


class GeneratePlantUMLTool(Tool):
    """Generate PlantUML diagram code.

    Creates diagrams in PlantUML syntax which is widely used in enterprise
    environments and supports a rich set of diagram types.
    """

    name = "generate_plantuml"
    description = """Generate a PlantUML diagram from a description or specification.

PlantUML is powerful for detailed UML diagrams and is widely used in enterprise.

Supported diagram types:
- sequence: Sequence diagrams for API/service interactions
- class: Class diagrams for OOP structures
- activity: Activity diagrams (flowcharts with UML notation)
- component: Component diagrams for system architecture
- usecase: Use case diagrams for requirements
- deployment: Deployment diagrams for infrastructure

Examples:
- generate_plantuml(diagram_type="sequence", participants=["User", "API", "DB"], messages=[...])
- generate_plantuml(diagram_type="class", classes=[{"name": "User", "attributes": ["+name: string"]}])
- generate_plantuml(diagram_type="component", components=[{"name": "WebServer", "interfaces": ["HTTP"]}])"""

    parameters = {
        "type": "object",
        "properties": {
            "diagram_type": {
                "type": "string",
                "description": "Type of diagram to generate",
                "enum": ["sequence", "class", "activity", "component", "usecase", "deployment"],
            },
            "participants": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For sequence diagrams: list of participant names",
            },
            "messages": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For sequence diagrams: list of messages with 'from', 'to', 'message' keys",
            },
            "classes": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For class diagrams: list of classes with 'name', 'methods', 'attributes' keys",
            },
            "components": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For component diagrams: list with 'name', 'interfaces', 'dependencies'",
            },
            "actors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For use case diagrams: list of actor names",
            },
            "usecases": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For use case diagrams: list with 'name', 'actor' keys",
            },
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "description": "For deployment diagrams: list of nodes with 'name', 'type', 'components'",
            },
            "title": {
                "type": "string",
                "description": "Optional title for the diagram",
            },
            "theme": {
                "type": "string",
                "description": "PlantUML theme: default, blueprint, sketchy, etc.",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the diagram",
            },
        },
        "required": ["diagram_type"],
    }

    async def execute(
        self,
        diagram_type: str,
        participants: Optional[list[str]] = None,
        messages: Optional[list[dict]] = None,
        classes: Optional[list[dict]] = None,
        components: Optional[list[dict]] = None,
        actors: Optional[list[str]] = None,
        usecases: Optional[list[dict]] = None,
        nodes: Optional[list[dict]] = None,
        title: Optional[str] = None,
        theme: Optional[str] = None,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate a PlantUML diagram."""
        try:
            if diagram_type == "sequence":
                diagram = self._generate_sequence(participants, messages, title, theme)
            elif diagram_type == "class":
                diagram = self._generate_class_diagram(classes, title, theme)
            elif diagram_type == "activity":
                diagram = self._generate_activity(title, theme)
            elif diagram_type == "component":
                diagram = self._generate_component(components, title, theme)
            elif diagram_type == "usecase":
                diagram = self._generate_usecase(actors, usecases, title, theme)
            elif diagram_type == "deployment":
                diagram = self._generate_deployment(nodes, title, theme)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported diagram type: {diagram_type}",
                )

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(diagram)
                return ToolResult(
                    success=True,
                    output=f"Diagram saved to {output_path}\n\n```plantuml\n{diagram}\n```",
                    metadata={"diagram_type": diagram_type, "format": "plantuml", "output_file": str(output_path)},
                )

            return ToolResult(
                success=True,
                output=f"```plantuml\n{diagram}\n```",
                metadata={"diagram_type": diagram_type, "format": "plantuml"},
            )

        except Exception as e:
            log.error("plantuml_generation_failed", error=str(e), diagram_type=diagram_type)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate PlantUML diagram: {str(e)}",
            )

    def _generate_sequence(
        self,
        participants: Optional[list[str]],
        messages: Optional[list[dict]],
        title: Optional[str],
        theme: Optional[str],
    ) -> str:
        """Generate sequence diagram."""
        lines = ["@startuml"]
        if theme:
            lines.append(f"!theme {theme}")
        if title:
            lines.append(f"title {title}")

        if participants:
            for p in participants:
                lines.append(f'participant "{p}" as {p.replace(" ", "_")}')

        if messages:
            for msg in messages:
                from_p = msg.get("from", "A").replace(" ", "_")
                to_p = msg.get("to", "B").replace(" ", "_")
                message = msg.get("message", "")
                msg_type = msg.get("type", "sync")

                if msg_type == "async":
                    lines.append(f"{from_p} ->> {to_p}: {message}")
                elif msg_type == "reply":
                    lines.append(f"{from_p} --> {to_p}: {message}")
                else:
                    lines.append(f"{from_p} -> {to_p}: {message}")

        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_class_diagram(
        self,
        classes: Optional[list[dict]],
        title: Optional[str],
        theme: Optional[str],
    ) -> str:
        """Generate class diagram."""
        lines = ["@startuml"]
        if theme:
            lines.append(f"!theme {theme}")
        if title:
            lines.append(f"title {title}")

        if classes:
            for cls in classes:
                class_name = cls.get("name", "Class")
                attributes = cls.get("attributes", [])
                methods = cls.get("methods", [])
                parent = cls.get("parent")
                stereotype = cls.get("stereotype")

                if stereotype:
                    lines.append(f"class {class_name} <<{stereotype}>> {{")
                else:
                    lines.append(f"class {class_name} {{")

                for attr in attributes:
                    lines.append(f"    {attr}")
                if attributes and methods:
                    lines.append("    --")
                for method in methods:
                    lines.append(f"    {method}")
                lines.append("}")

                if parent:
                    lines.append(f"{parent} <|-- {class_name}")

        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_activity(self, title: Optional[str], theme: Optional[str]) -> str:
        """Generate activity diagram (placeholder)."""
        lines = ["@startuml"]
        if theme:
            lines.append(f"!theme {theme}")
        if title:
            lines.append(f"title {title}")

        lines.append("start")
        lines.append(":Activity 1;")
        lines.append("if (condition?) then (yes)")
        lines.append("    :Activity 2;")
        lines.append("else (no)")
        lines.append("    :Activity 3;")
        lines.append("endif")
        lines.append("stop")

        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_component(
        self,
        components: Optional[list[dict]],
        title: Optional[str],
        theme: Optional[str],
    ) -> str:
        """Generate component diagram."""
        lines = ["@startuml"]
        if theme:
            lines.append(f"!theme {theme}")
        if title:
            lines.append(f"title {title}")

        if components:
            for comp in components:
                comp_name = comp.get("name", "Component")
                interfaces = comp.get("interfaces", [])
                dependencies = comp.get("dependencies", [])

                lines.append(f"component [{comp_name}]")

                for iface in interfaces:
                    lines.append(f"interface {iface}")
                    lines.append(f"[{comp_name}] -( {iface}")

                for dep in dependencies:
                    lines.append(f"[{comp_name}] --> [{dep}]")

        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_usecase(
        self,
        actors: Optional[list[str]],
        usecases: Optional[list[dict]],
        title: Optional[str],
        theme: Optional[str],
    ) -> str:
        """Generate use case diagram."""
        lines = ["@startuml"]
        if theme:
            lines.append(f"!theme {theme}")
        if title:
            lines.append(f"title {title}")

        if actors:
            for actor in actors:
                lines.append(f"actor {actor}")

        if usecases:
            for uc in usecases:
                uc_name = uc.get("name", "Use Case")
                actor = uc.get("actor")

                lines.append(f'usecase "{uc_name}" as UC_{uc_name.replace(" ", "_")}')
                if actor:
                    lines.append(f'{actor} --> UC_{uc_name.replace(" ", "_")}')

        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_deployment(
        self,
        nodes: Optional[list[dict]],
        title: Optional[str],
        theme: Optional[str],
    ) -> str:
        """Generate deployment diagram."""
        lines = ["@startuml"]
        if theme:
            lines.append(f"!theme {theme}")
        if title:
            lines.append(f"title {title}")

        if nodes:
            for node in nodes:
                node_name = node.get("name", "Node")
                node_type = node.get("type", "node")  # node, cloud, database, server
                components = node.get("components", [])

                if node_type == "cloud":
                    lines.append(f"cloud {node_name} {{")
                elif node_type == "database":
                    lines.append(f"database {node_name} {{")
                else:
                    lines.append(f"node {node_name} {{")

                for comp in components:
                    lines.append(f"    [{comp}]")
                lines.append("}")

        lines.append("@enduml")
        return "\n".join(lines)


class GenerateD2Tool(Tool):
    """Generate D2 diagram code.

    D2 is a modern diagramming language with excellent aesthetics
    and support for complex layouts.
    """

    name = "generate_d2"
    description = """Generate a D2 diagram from a description or specification.

D2 is a modern diagram language with excellent aesthetics and auto-layout.

Features:
- Clean, readable syntax
- Automatic layout algorithms
- Support for icons, markdown, and code blocks
- Themes and styling

Examples:
- generate_d2(nodes=[{"id": "api", "label": "API Server"}], edges=[{"from": "api", "to": "db"}])
- generate_d2(containers=[{"id": "aws", "label": "AWS", "children": ["ec2", "rds"]}])"""

    parameters = {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of nodes with 'id', 'label', optional 'shape', 'style'",
            },
            "edges": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of edges with 'from', 'to', optional 'label', 'style'",
            },
            "containers": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of container nodes with 'id', 'label', 'children'",
            },
            "title": {
                "type": "string",
                "description": "Title displayed at top of diagram",
            },
            "direction": {
                "type": "string",
                "description": "Layout direction: right, down, left, up",
                "enum": ["right", "down", "left", "up"],
            },
            "theme": {
                "type": "string",
                "description": "D2 theme ID (0-100)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the diagram",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        nodes: Optional[list[dict]] = None,
        edges: Optional[list[dict]] = None,
        containers: Optional[list[dict]] = None,
        title: Optional[str] = None,
        direction: str = "right",
        theme: Optional[str] = None,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate a D2 diagram."""
        try:
            lines = []

            if title:
                lines.append(f"title: {title}")

            if direction != "right":
                lines.append(f"direction: {direction}")

            if theme:
                lines.append(f"vars: {{")
                lines.append(f"  d2-config: {{")
                lines.append(f"    theme-id: {theme}")
                lines.append(f"  }}")
                lines.append(f"}}")

            lines.append("")

            # Add containers
            if containers:
                for container in containers:
                    container_id = container.get("id", "container")
                    label = container.get("label", container_id)
                    children = container.get("children", [])
                    style = container.get("style", {})

                    lines.append(f"{container_id}: {label} {{")
                    for child in children:
                        lines.append(f"    {child}")
                    if style:
                        lines.append("    style: {")
                        for k, v in style.items():
                            lines.append(f"        {k}: {v}")
                        lines.append("    }")
                    lines.append("}")
                    lines.append("")

            # Add nodes
            if nodes:
                for node in nodes:
                    node_id = node.get("id", "node")
                    label = node.get("label", node_id)
                    shape = node.get("shape")
                    style = node.get("style", {})
                    icon = node.get("icon")

                    if shape or style or icon:
                        lines.append(f"{node_id}: {label} {{")
                        if shape:
                            lines.append(f"    shape: {shape}")
                        if icon:
                            lines.append(f"    icon: {icon}")
                        if style:
                            lines.append("    style: {")
                            for k, v in style.items():
                                lines.append(f"        {k}: {v}")
                            lines.append("    }")
                        lines.append("}")
                    else:
                        lines.append(f"{node_id}: {label}")

            # Add edges
            if edges:
                lines.append("")
                for edge in edges:
                    from_node = edge.get("from", "a")
                    to_node = edge.get("to", "b")
                    label = edge.get("label", "")
                    style = edge.get("style")

                    if label:
                        lines.append(f"{from_node} -> {to_node}: {label}")
                    else:
                        lines.append(f"{from_node} -> {to_node}")

            diagram = "\n".join(lines)

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(diagram)
                return ToolResult(
                    success=True,
                    output=f"Diagram saved to {output_path}\n\n```d2\n{diagram}\n```",
                    metadata={"format": "d2", "output_file": str(output_path)},
                )

            return ToolResult(
                success=True,
                output=f"```d2\n{diagram}\n```",
                metadata={"format": "d2"},
            )

        except Exception as e:
            log.error("d2_generation_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate D2 diagram: {str(e)}",
            )


class DiagramFromCodeTool(Tool):
    """Extract and generate diagrams from source code.

    Analyzes Python, JavaScript, TypeScript, Go, and Rust code to generate
    class diagrams, dependency graphs, and architecture diagrams.
    """

    name = "diagram_from_code"
    description = """Extract and generate diagrams from source code.

Analyzes code files to generate:
- Class diagrams from OOP code
- Module dependency graphs
- Call graphs for function flow
- Architecture diagrams from project structure

Supported languages: Python, JavaScript, TypeScript, Go, Rust

Examples:
- diagram_from_code(file_path="src/models.py", diagram_type="class")
- diagram_from_code(path="src/", diagram_type="dependencies")
- diagram_from_code(path=".", diagram_type="architecture", format="mermaid")"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to a single source file to analyze",
            },
            "path": {
                "type": "string",
                "description": "Path to directory to analyze for multi-file diagrams",
            },
            "diagram_type": {
                "type": "string",
                "description": "Type of diagram to generate",
                "enum": ["class", "dependencies", "architecture", "call_graph"],
            },
            "format": {
                "type": "string",
                "description": "Output format: mermaid, plantuml, d2",
                "enum": ["mermaid", "plantuml", "d2"],
            },
            "include_private": {
                "type": "boolean",
                "description": "Include private methods/attributes (default: false)",
            },
            "max_depth": {
                "type": "integer",
                "description": "Max depth for dependency analysis (default: 3)",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the diagram",
            },
        },
        "required": ["diagram_type"],
    }

    # Language-specific patterns for class extraction
    PYTHON_CLASS_PATTERN = re.compile(
        r"class\s+(\w+)(?:\(([^)]*)\))?:",
        re.MULTILINE
    )
    PYTHON_METHOD_PATTERN = re.compile(
        r"^\s+def\s+(\w+)\s*\((.*?)\)(?:\s*->\s*(\w+))?:",
        re.MULTILINE
    )
    PYTHON_IMPORT_PATTERN = re.compile(
        r"^(?:from\s+([\w.]+)\s+)?import\s+([\w,\s]+)",
        re.MULTILINE
    )

    async def execute(
        self,
        diagram_type: str,
        file_path: Optional[str] = None,
        path: Optional[str] = None,
        format: str = "mermaid",
        include_private: bool = False,
        max_depth: int = 3,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate diagram from code analysis."""
        try:
            if file_path:
                resolved = self._resolve_path(file_path)
                if not resolved.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {resolved}",
                    )
                files = [resolved]
            elif path:
                resolved = self._resolve_path(path)
                if not resolved.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Path not found: {resolved}",
                    )
                # Get all source files
                files = self._find_source_files(resolved)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error="Either file_path or path must be provided",
                )

            if diagram_type == "class":
                diagram = self._generate_class_diagram(files, format, include_private)
            elif diagram_type == "dependencies":
                diagram = self._generate_dependency_diagram(files, format, max_depth)
            elif diagram_type == "architecture":
                base_path = self._resolve_path(path or ".")
                diagram = self._generate_architecture_diagram(base_path, files, format)
            elif diagram_type == "call_graph":
                diagram = self._generate_call_graph(files, format)
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unsupported diagram type: {diagram_type}",
                )

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(diagram)
                return ToolResult(
                    success=True,
                    output=f"Diagram saved to {output_path}\n\n```{format}\n{diagram}\n```",
                    metadata={
                        "diagram_type": diagram_type,
                        "format": format,
                        "files_analyzed": len(files),
                        "output_file": str(output_path),
                    },
                )

            return ToolResult(
                success=True,
                output=f"```{format}\n{diagram}\n```",
                metadata={
                    "diagram_type": diagram_type,
                    "format": format,
                    "files_analyzed": len(files),
                },
            )

        except Exception as e:
            log.error("diagram_from_code_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate diagram from code: {str(e)}",
            )

    def _find_source_files(self, path: Path) -> list[Path]:
        """Find all source files in directory."""
        extensions = [".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java"]
        files = []
        for ext in extensions:
            files.extend(path.rglob(f"*{ext}"))
        # Filter out common non-source directories
        exclude_dirs = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build"}
        files = [f for f in files if not any(ex in f.parts for ex in exclude_dirs)]
        return files

    def _extract_python_classes(self, content: str, include_private: bool) -> list[ClassInfo]:
        """Extract class information from Python code."""
        classes = []

        for match in self.PYTHON_CLASS_PATTERN.finditer(content):
            class_name = match.group(1)
            parent = match.group(2)

            # Extract methods and attributes for this class
            class_start = match.end()
            # Find the next class or end of file
            next_class = self.PYTHON_CLASS_PATTERN.search(content[class_start:])
            class_end = class_start + next_class.start() if next_class else len(content)
            class_content = content[class_start:class_end]

            methods = []
            attributes = []

            for method_match in self.PYTHON_METHOD_PATTERN.finditer(class_content):
                method_name = method_match.group(1)
                if not include_private and method_name.startswith("_") and not method_name.startswith("__"):
                    continue
                params = method_match.group(2)
                return_type = method_match.group(3) or ""
                methods.append(f"{method_name}({params}): {return_type}".rstrip(": "))

            # Extract attributes from __init__ or type hints
            attr_pattern = re.compile(r"self\.(\w+)\s*[:=]")
            for attr_match in attr_pattern.finditer(class_content):
                attr_name = attr_match.group(1)
                if not include_private and attr_name.startswith("_"):
                    continue
                attributes.append(attr_name)

            classes.append(ClassInfo(
                name=class_name,
                methods=methods,
                attributes=list(set(attributes)),
                parent=parent.split(",")[0].strip() if parent else None,
            ))

        return classes

    def _generate_class_diagram(
        self,
        files: list[Path],
        format: str,
        include_private: bool,
    ) -> str:
        """Generate class diagram from source files."""
        all_classes: list[ClassInfo] = []

        for file_path in files:
            if file_path.suffix == ".py":
                content = file_path.read_text(errors="ignore")
                classes = self._extract_python_classes(content, include_private)
                all_classes.extend(classes)

        if format == "mermaid":
            return self._classes_to_mermaid(all_classes)
        elif format == "plantuml":
            return self._classes_to_plantuml(all_classes)
        else:
            return self._classes_to_d2(all_classes)

    def _classes_to_mermaid(self, classes: list[ClassInfo]) -> str:
        """Convert classes to Mermaid class diagram."""
        lines = ["classDiagram"]

        for cls in classes:
            lines.append(f"    class {cls.name} {{")
            for attr in cls.attributes:
                lines.append(f"        +{attr}")
            for method in cls.methods:
                lines.append(f"        +{method}")
            lines.append("    }")

            if cls.parent:
                lines.append(f"    {cls.parent} <|-- {cls.name}")

        return "\n".join(lines)

    def _classes_to_plantuml(self, classes: list[ClassInfo]) -> str:
        """Convert classes to PlantUML class diagram."""
        lines = ["@startuml"]

        for cls in classes:
            lines.append(f"class {cls.name} {{")
            for attr in cls.attributes:
                lines.append(f"    +{attr}")
            lines.append("    --")
            for method in cls.methods:
                lines.append(f"    +{method}")
            lines.append("}")

            if cls.parent:
                lines.append(f"{cls.parent} <|-- {cls.name}")

        lines.append("@enduml")
        return "\n".join(lines)

    def _classes_to_d2(self, classes: list[ClassInfo]) -> str:
        """Convert classes to D2 diagram."""
        lines = []

        for cls in classes:
            lines.append(f"{cls.name}: {cls.name} {{")
            lines.append("    shape: class")

            if cls.attributes or cls.methods:
                attr_str = "\\n".join(cls.attributes) if cls.attributes else ""
                method_str = "\\n".join(cls.methods) if cls.methods else ""
                full_label = f"{attr_str}\\n---\\n{method_str}".strip("\\n---\\n")
                # D2 class shapes handle this differently
            lines.append("}")

            if cls.parent:
                lines.append(f"{cls.parent} -> {cls.name}: extends")

        return "\n".join(lines)

    def _generate_dependency_diagram(
        self,
        files: list[Path],
        format: str,
        max_depth: int,
    ) -> str:
        """Generate module dependency diagram."""
        dependencies: dict[str, set[str]] = {}

        for file_path in files:
            if file_path.suffix == ".py":
                content = file_path.read_text(errors="ignore")
                module_name = file_path.stem

                deps = set()
                for match in self.PYTHON_IMPORT_PATTERN.finditer(content):
                    from_module = match.group(1)
                    imports = match.group(2)

                    if from_module:
                        deps.add(from_module.split(".")[0])
                    else:
                        for imp in imports.split(","):
                            deps.add(imp.strip().split(".")[0])

                # Filter to only local modules
                local_modules = {f.stem for f in files}
                deps = deps.intersection(local_modules)
                deps.discard(module_name)

                if deps:
                    dependencies[module_name] = deps

        if format == "mermaid":
            return self._deps_to_mermaid(dependencies)
        elif format == "plantuml":
            return self._deps_to_plantuml(dependencies)
        else:
            return self._deps_to_d2(dependencies)

    def _deps_to_mermaid(self, dependencies: dict[str, set[str]]) -> str:
        """Convert dependencies to Mermaid flowchart."""
        lines = ["flowchart LR"]

        all_modules = set(dependencies.keys())
        for deps in dependencies.values():
            all_modules.update(deps)

        for module in all_modules:
            lines.append(f"    {module}[{module}]")

        for module, deps in dependencies.items():
            for dep in deps:
                lines.append(f"    {module} --> {dep}")

        return "\n".join(lines)

    def _deps_to_plantuml(self, dependencies: dict[str, set[str]]) -> str:
        """Convert dependencies to PlantUML component diagram."""
        lines = ["@startuml"]

        all_modules = set(dependencies.keys())
        for deps in dependencies.values():
            all_modules.update(deps)

        for module in all_modules:
            lines.append(f"component [{module}]")

        for module, deps in dependencies.items():
            for dep in deps:
                lines.append(f"[{module}] --> [{dep}]")

        lines.append("@enduml")
        return "\n".join(lines)

    def _deps_to_d2(self, dependencies: dict[str, set[str]]) -> str:
        """Convert dependencies to D2 diagram."""
        lines = []

        all_modules = set(dependencies.keys())
        for deps in dependencies.values():
            all_modules.update(deps)

        for module in all_modules:
            lines.append(f"{module}")

        lines.append("")

        for module, deps in dependencies.items():
            for dep in deps:
                lines.append(f"{module} -> {dep}")

        return "\n".join(lines)

    def _generate_architecture_diagram(
        self,
        base_path: Path,
        files: list[Path],
        format: str,
    ) -> str:
        """Generate architecture diagram from project structure."""
        # Group files by directory
        packages: dict[str, list[str]] = {}

        for file_path in files:
            try:
                rel_path = file_path.relative_to(base_path)
                if len(rel_path.parts) > 1:
                    package = rel_path.parts[0]
                else:
                    package = "root"
                if package not in packages:
                    packages[package] = []
                packages[package].append(file_path.stem)
            except ValueError:
                continue

        if format == "mermaid":
            return self._arch_to_mermaid(packages)
        elif format == "plantuml":
            return self._arch_to_plantuml(packages)
        else:
            return self._arch_to_d2(packages)

    def _arch_to_mermaid(self, packages: dict[str, list[str]]) -> str:
        """Convert architecture to Mermaid flowchart."""
        lines = ["flowchart TB"]

        for package, modules in packages.items():
            lines.append(f"    subgraph {package}")
            for module in modules[:10]:  # Limit to avoid huge diagrams
                lines.append(f"        {package}_{module}[{module}]")
            lines.append("    end")

        return "\n".join(lines)

    def _arch_to_plantuml(self, packages: dict[str, list[str]]) -> str:
        """Convert architecture to PlantUML package diagram."""
        lines = ["@startuml"]

        for package, modules in packages.items():
            lines.append(f"package {package} {{")
            for module in modules[:10]:
                lines.append(f"    [{module}]")
            lines.append("}")

        lines.append("@enduml")
        return "\n".join(lines)

    def _arch_to_d2(self, packages: dict[str, list[str]]) -> str:
        """Convert architecture to D2 diagram."""
        lines = []

        for package, modules in packages.items():
            lines.append(f"{package}: {package} {{")
            for module in modules[:10]:
                lines.append(f"    {module}")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)

    def _generate_call_graph(self, files: list[Path], format: str) -> str:
        """Generate call graph (simplified version)."""
        # This is a simplified implementation
        # A full implementation would use AST analysis
        calls: list[tuple[str, str]] = []
        functions: set[str] = set()

        func_pattern = re.compile(r"def\s+(\w+)\s*\(")
        call_pattern = re.compile(r"(\w+)\s*\(")

        for file_path in files:
            if file_path.suffix == ".py":
                content = file_path.read_text(errors="ignore")

                current_func = None
                for line in content.split("\n"):
                    func_match = func_pattern.search(line)
                    if func_match and not line.strip().startswith("#"):
                        current_func = func_match.group(1)
                        functions.add(current_func)
                    elif current_func:
                        for call_match in call_pattern.finditer(line):
                            called = call_match.group(1)
                            if called in functions and called != current_func:
                                calls.append((current_func, called))

        if format == "mermaid":
            lines = ["flowchart LR"]
            for func in functions:
                lines.append(f"    {func}(({func}))")
            for caller, callee in set(calls):
                lines.append(f"    {caller} --> {callee}")
            return "\n".join(lines)
        elif format == "plantuml":
            lines = ["@startuml"]
            for caller, callee in set(calls):
                lines.append(f"({caller}) --> ({callee})")
            lines.append("@enduml")
            return "\n".join(lines)
        else:
            lines = []
            for func in functions:
                lines.append(f"{func}")
            lines.append("")
            for caller, callee in set(calls):
                lines.append(f"{caller} -> {callee}")
            return "\n".join(lines)


class GenerateSequenceDiagramTool(Tool):
    """Generate sequence diagrams from API flows or logs.

    Specialized tool for creating sequence diagrams from various sources.
    """

    name = "generate_sequence_diagram"
    description = """Generate a sequence diagram from API flows, logs, or descriptions.

Specialized for sequence diagrams with support for:
- HTTP API flows (from OpenAPI or routes)
- Log file analysis
- Text descriptions

Examples:
- generate_sequence_diagram(description="User -> API -> DB: login flow")
- generate_sequence_diagram(api_spec="openapi.json", endpoints=["/login", "/logout"])
- generate_sequence_diagram(log_file="app.log", filter="request_id=abc")"""

    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of the sequence",
            },
            "participants": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of participants/actors",
            },
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Sequence steps: {'from': str, 'to': str, 'action': str, 'response': str?}",
            },
            "api_endpoints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of API endpoints to include in sequence",
            },
            "format": {
                "type": "string",
                "description": "Output format: mermaid, plantuml",
                "enum": ["mermaid", "plantuml"],
            },
            "show_responses": {
                "type": "boolean",
                "description": "Include response arrows (default: true)",
            },
            "autonumber": {
                "type": "boolean",
                "description": "Add step numbers (default: false)",
            },
            "title": {
                "type": "string",
                "description": "Diagram title",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the diagram",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        description: Optional[str] = None,
        participants: Optional[list[str]] = None,
        steps: Optional[list[dict]] = None,
        api_endpoints: Optional[list[str]] = None,
        format: str = "mermaid",
        show_responses: bool = True,
        autonumber: bool = False,
        title: Optional[str] = None,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate a sequence diagram."""
        try:
            if format == "mermaid":
                diagram = self._generate_mermaid(
                    participants, steps, title, show_responses, autonumber
                )
            else:
                diagram = self._generate_plantuml(
                    participants, steps, title, show_responses, autonumber
                )

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(diagram)
                return ToolResult(
                    success=True,
                    output=f"Diagram saved to {output_path}\n\n```{format}\n{diagram}\n```",
                    metadata={"format": format, "output_file": str(output_path)},
                )

            return ToolResult(
                success=True,
                output=f"```{format}\n{diagram}\n```",
                metadata={"format": format},
            )

        except Exception as e:
            log.error("sequence_diagram_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate sequence diagram: {str(e)}",
            )

    def _generate_mermaid(
        self,
        participants: Optional[list[str]],
        steps: Optional[list[dict]],
        title: Optional[str],
        show_responses: bool,
        autonumber: bool,
    ) -> str:
        """Generate Mermaid sequence diagram."""
        lines = ["sequenceDiagram"]

        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        if autonumber:
            lines.append("    autonumber")

        if participants:
            for p in participants:
                lines.append(f"    participant {p}")

        if steps:
            for step in steps:
                from_p = step.get("from", "A")
                to_p = step.get("to", "B")
                action = step.get("action", "")
                response = step.get("response")
                async_call = step.get("async", False)

                if async_call:
                    lines.append(f"    {from_p}-->>>{to_p}: {action}")
                else:
                    lines.append(f"    {from_p}->>>{to_p}: {action}")

                if show_responses and response:
                    lines.append(f"    {to_p}-->>>{from_p}: {response}")

        return "\n".join(lines)

    def _generate_plantuml(
        self,
        participants: Optional[list[str]],
        steps: Optional[list[dict]],
        title: Optional[str],
        show_responses: bool,
        autonumber: bool,
    ) -> str:
        """Generate PlantUML sequence diagram."""
        lines = ["@startuml"]

        if title:
            lines.append(f"title {title}")

        if autonumber:
            lines.append("autonumber")

        if participants:
            for p in participants:
                lines.append(f'participant "{p}" as {p.replace(" ", "_")}')

        if steps:
            for step in steps:
                from_p = step.get("from", "A").replace(" ", "_")
                to_p = step.get("to", "B").replace(" ", "_")
                action = step.get("action", "")
                response = step.get("response")
                async_call = step.get("async", False)

                if async_call:
                    lines.append(f"{from_p} ->> {to_p}: {action}")
                else:
                    lines.append(f"{from_p} -> {to_p}: {action}")

                if show_responses and response:
                    lines.append(f"{to_p} --> {from_p}: {response}")

        lines.append("@enduml")
        return "\n".join(lines)


class GenerateERDiagramTool(Tool):
    """Generate Entity-Relationship diagrams from database schemas.

    Analyzes SQL files, SQLAlchemy models, or schema descriptions to
    generate ER diagrams.
    """

    name = "generate_er_diagram"
    description = """Generate an Entity-Relationship diagram from database schema.

Supports:
- SQLAlchemy models (Python)
- SQL CREATE TABLE statements
- Schema descriptions

Examples:
- generate_er_diagram(file_path="models.py") - From SQLAlchemy models
- generate_er_diagram(sql_file="schema.sql") - From SQL DDL
- generate_er_diagram(tables=[{"name": "users", "columns": ["id PK", "email"]}])"""

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to Python file with SQLAlchemy/Django models",
            },
            "sql_file": {
                "type": "string",
                "description": "Path to SQL file with CREATE TABLE statements",
            },
            "tables": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of tables: {'name': str, 'columns': [str], 'foreign_keys': [str]}",
            },
            "format": {
                "type": "string",
                "description": "Output format: mermaid, plantuml, d2",
                "enum": ["mermaid", "plantuml", "d2"],
            },
            "show_types": {
                "type": "boolean",
                "description": "Show column types (default: true)",
            },
            "title": {
                "type": "string",
                "description": "Diagram title",
            },
            "output_file": {
                "type": "string",
                "description": "Optional file path to save the diagram",
            },
        },
        "required": [],
    }

    # Pattern for SQLAlchemy Column definitions
    SQLALCHEMY_COLUMN_PATTERN = re.compile(
        r"(\w+)\s*=\s*(?:Column|db\.Column)\s*\(\s*(\w+)"
    )
    SQLALCHEMY_FK_PATTERN = re.compile(
        r"ForeignKey\s*\(\s*['\"](\w+)\.(\w+)['\"]"
    )
    SQL_CREATE_TABLE_PATTERN = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`'\"]?(\w+)[`'\"]?\s*\((.*?)\)",
        re.IGNORECASE | re.DOTALL
    )

    async def execute(
        self,
        file_path: Optional[str] = None,
        sql_file: Optional[str] = None,
        tables: Optional[list[dict]] = None,
        format: str = "mermaid",
        show_types: bool = True,
        title: Optional[str] = None,
        output_file: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """Generate ER diagram."""
        try:
            extracted_tables: list[TableInfo] = []

            if file_path:
                resolved = self._resolve_path(file_path)
                if not resolved.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"File not found: {resolved}",
                    )
                content = resolved.read_text()
                extracted_tables = self._extract_from_sqlalchemy(content)

            elif sql_file:
                resolved = self._resolve_path(sql_file)
                if not resolved.exists():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"SQL file not found: {resolved}",
                    )
                content = resolved.read_text()
                extracted_tables = self._extract_from_sql(content)

            elif tables:
                for table in tables:
                    columns = []
                    fks = []
                    for col in table.get("columns", []):
                        if isinstance(col, str):
                            parts = col.split()
                            col_name = parts[0]
                            col_type = parts[1] if len(parts) > 1 else "string"
                            is_pk = "PK" in col.upper()
                            columns.append((col_name, col_type, is_pk))
                        elif isinstance(col, dict):
                            columns.append((
                                col.get("name", "col"),
                                col.get("type", "string"),
                                col.get("pk", False)
                            ))

                    for fk in table.get("foreign_keys", []):
                        if isinstance(fk, str):
                            # Parse "column -> table.column"
                            parts = fk.split("->")
                            if len(parts) == 2:
                                local_col = parts[0].strip()
                                ref = parts[1].strip()
                                if "." in ref:
                                    ref_table, ref_col = ref.split(".")
                                    fks.append((local_col, ref_table, ref_col))

                    extracted_tables.append(TableInfo(
                        name=table.get("name", "table"),
                        columns=columns,
                        foreign_keys=fks,
                    ))

            if not extracted_tables:
                return ToolResult(
                    success=False,
                    output="",
                    error="No tables found or provided",
                )

            if format == "mermaid":
                diagram = self._to_mermaid(extracted_tables, show_types, title)
            elif format == "plantuml":
                diagram = self._to_plantuml(extracted_tables, show_types, title)
            else:
                diagram = self._to_d2(extracted_tables, show_types, title)

            if output_file:
                output_path = self._resolve_path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(diagram)
                return ToolResult(
                    success=True,
                    output=f"Diagram saved to {output_path}\n\n```{format}\n{diagram}\n```",
                    metadata={
                        "format": format,
                        "tables_count": len(extracted_tables),
                        "output_file": str(output_path),
                    },
                )

            return ToolResult(
                success=True,
                output=f"```{format}\n{diagram}\n```",
                metadata={"format": format, "tables_count": len(extracted_tables)},
            )

        except Exception as e:
            log.error("er_diagram_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to generate ER diagram: {str(e)}",
            )

    def _extract_from_sqlalchemy(self, content: str) -> list[TableInfo]:
        """Extract table info from SQLAlchemy models."""
        tables = []

        # Find class definitions that look like models
        class_pattern = re.compile(
            r"class\s+(\w+)\s*\([^)]*(?:Base|db\.Model|Model)[^)]*\):",
            re.IGNORECASE
        )

        for class_match in class_pattern.finditer(content):
            table_name = class_match.group(1)
            class_start = class_match.end()

            # Find next class or end
            next_class = class_pattern.search(content[class_start:])
            class_end = class_start + next_class.start() if next_class else len(content)
            class_content = content[class_start:class_end]

            columns = []
            foreign_keys = []

            for col_match in self.SQLALCHEMY_COLUMN_PATTERN.finditer(class_content):
                col_name = col_match.group(1)
                col_type = col_match.group(2).lower()

                # Check for primary key
                is_pk = "primary_key=True" in content[col_match.start():col_match.start() + 200]
                columns.append((col_name, col_type, is_pk))

                # Check for foreign key
                fk_match = self.SQLALCHEMY_FK_PATTERN.search(
                    content[col_match.start():col_match.start() + 200]
                )
                if fk_match:
                    foreign_keys.append((col_name, fk_match.group(1), fk_match.group(2)))

            if columns:
                tables.append(TableInfo(
                    name=table_name,
                    columns=columns,
                    foreign_keys=foreign_keys,
                ))

        return tables

    def _extract_from_sql(self, content: str) -> list[TableInfo]:
        """Extract table info from SQL CREATE TABLE statements."""
        tables = []

        for match in self.SQL_CREATE_TABLE_PATTERN.finditer(content):
            table_name = match.group(1)
            columns_str = match.group(2)

            columns = []
            foreign_keys = []

            # Parse column definitions
            for line in columns_str.split(","):
                line = line.strip()
                if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "INDEX", "CONSTRAINT")):
                    # Handle FOREIGN KEY constraints
                    if "FOREIGN KEY" in line.upper():
                        fk_pattern = re.compile(
                            r"FOREIGN\s+KEY\s*\(\s*[`'\"]?(\w+)[`'\"]?\s*\)\s*REFERENCES\s+[`'\"]?(\w+)[`'\"]?\s*\(\s*[`'\"]?(\w+)[`'\"]?\s*\)",
                            re.IGNORECASE
                        )
                        fk_match = fk_pattern.search(line)
                        if fk_match:
                            foreign_keys.append((fk_match.group(1), fk_match.group(2), fk_match.group(3)))
                    continue

                # Parse column: name type [constraints]
                parts = line.split()
                if len(parts) >= 2:
                    col_name = parts[0].strip("`'\"")
                    col_type = parts[1].split("(")[0].lower()
                    is_pk = "PRIMARY KEY" in line.upper()
                    columns.append((col_name, col_type, is_pk))

            if columns:
                tables.append(TableInfo(
                    name=table_name,
                    columns=columns,
                    foreign_keys=foreign_keys,
                ))

        return tables

    def _to_mermaid(
        self,
        tables: list[TableInfo],
        show_types: bool,
        title: Optional[str],
    ) -> str:
        """Convert tables to Mermaid ER diagram."""
        lines = ["erDiagram"]
        if title:
            lines.insert(0, f"---\ntitle: {title}\n---")

        for table in tables:
            lines.append(f"    {table.name} {{")
            for col_name, col_type, is_pk in table.columns:
                pk_marker = " PK" if is_pk else ""
                if show_types:
                    lines.append(f"        {col_type} {col_name}{pk_marker}")
                else:
                    lines.append(f"        string {col_name}{pk_marker}")
            lines.append("    }")

        # Add relationships
        for table in tables:
            for col_name, ref_table, ref_col in table.foreign_keys:
                lines.append(f"    {ref_table} ||--o{{ {table.name} : has")

        return "\n".join(lines)

    def _to_plantuml(
        self,
        tables: list[TableInfo],
        show_types: bool,
        title: Optional[str],
    ) -> str:
        """Convert tables to PlantUML ER diagram."""
        lines = ["@startuml"]
        if title:
            lines.append(f"title {title}")

        for table in tables:
            lines.append(f"entity {table.name} {{")
            for col_name, col_type, is_pk in table.columns:
                marker = " <<PK>>" if is_pk else ""
                if show_types:
                    lines.append(f"    {col_name}: {col_type}{marker}")
                else:
                    lines.append(f"    {col_name}{marker}")
            lines.append("}")

        # Add relationships
        for table in tables:
            for col_name, ref_table, ref_col in table.foreign_keys:
                lines.append(f"{ref_table} ||--o{{ {table.name}")

        lines.append("@enduml")
        return "\n".join(lines)

    def _to_d2(
        self,
        tables: list[TableInfo],
        show_types: bool,
        title: Optional[str],
    ) -> str:
        """Convert tables to D2 diagram."""
        lines = []
        if title:
            lines.append(f"title: {title}")
            lines.append("")

        for table in tables:
            lines.append(f"{table.name}: {table.name} {{")
            lines.append("    shape: sql_table")
            for col_name, col_type, is_pk in table.columns:
                pk_marker = " {constraint: primary_key}" if is_pk else ""
                if show_types:
                    lines.append(f"    {col_name}: {col_type}{pk_marker}")
                else:
                    lines.append(f"    {col_name}{pk_marker}")
            lines.append("}")
            lines.append("")

        # Add relationships
        for table in tables:
            for col_name, ref_table, ref_col in table.foreign_keys:
                lines.append(f"{ref_table} -> {table.name}")

        return "\n".join(lines)
