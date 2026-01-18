"""Tests for diagram generation tools (Phase 11)."""

import pytest
import tempfile
from pathlib import Path

from sindri.tools.diagrams import (
    GenerateMermaidTool,
    GeneratePlantUMLTool,
    GenerateD2Tool,
    DiagramFromCodeTool,
    GenerateSequenceDiagramTool,
    GenerateERDiagramTool,
)


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateMermaidTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateMermaidTool:
    """Test suite for Mermaid diagram generation."""

    @pytest.fixture
    def tool(self):
        return GenerateMermaidTool()

    @pytest.mark.asyncio
    async def test_sequence_diagram_basic(self, tool):
        """Test basic sequence diagram generation."""
        result = await tool.execute(
            diagram_type="sequence",
            participants=["User", "API", "Database"],
            messages=[
                {"from": "User", "to": "API", "message": "Login request"},
                {"from": "API", "to": "Database", "message": "Query user"},
                {"from": "Database", "to": "API", "message": "User data", "type": "reply"},
            ],
            title="Login Flow",
        )

        assert result.success
        assert "sequenceDiagram" in result.output
        assert "participant User" in result.output
        assert "Login Flow" in result.output
        assert "Login request" in result.output

    @pytest.mark.asyncio
    async def test_sequence_diagram_async_messages(self, tool):
        """Test sequence diagram with async messages."""
        result = await tool.execute(
            diagram_type="sequence",
            messages=[
                {"from": "A", "to": "B", "message": "Async call", "type": "async"},
            ],
        )

        assert result.success
        assert "-->>>" in result.output  # Mermaid async arrow

    @pytest.mark.asyncio
    async def test_flowchart_basic(self, tool):
        """Test basic flowchart generation."""
        result = await tool.execute(
            diagram_type="flowchart",
            nodes=[
                {"id": "A", "label": "Start"},
                {"id": "B", "label": "Process"},
                {"id": "C", "label": "End"},
            ],
            edges=[
                {"from": "A", "to": "B"},
                {"from": "B", "to": "C", "label": "Done"},
            ],
            direction="TB",
        )

        assert result.success
        assert "flowchart TB" in result.output
        assert "A[Start]" in result.output
        assert "-->|Done|" in result.output

    @pytest.mark.asyncio
    async def test_flowchart_shapes(self, tool):
        """Test flowchart with different shapes."""
        result = await tool.execute(
            diagram_type="flowchart",
            nodes=[
                {"id": "A", "label": "Start", "shape": "round"},
                {"id": "B", "label": "Decision?", "shape": "diamond"},
                {"id": "C", "label": "Process", "shape": "rect"},
                {"id": "D", "label": "Event", "shape": "circle"},
            ],
            edges=[
                {"from": "A", "to": "B"},
                {"from": "B", "to": "C"},
                {"from": "B", "to": "D"},
            ],
        )

        assert result.success
        assert "A(Start)" in result.output  # round shape
        assert "B{Decision?}" in result.output  # diamond shape
        assert "C[Process]" in result.output  # rect shape
        assert "D((Event))" in result.output  # circle shape

    @pytest.mark.asyncio
    async def test_flowchart_edge_types(self, tool):
        """Test flowchart with different edge types."""
        result = await tool.execute(
            diagram_type="flowchart",
            nodes=[
                {"id": "A", "label": "A"},
                {"id": "B", "label": "B"},
                {"id": "C", "label": "C"},
                {"id": "D", "label": "D"},
            ],
            edges=[
                {"from": "A", "to": "B", "type": "arrow"},
                {"from": "B", "to": "C", "type": "dotted"},
                {"from": "C", "to": "D", "type": "thick"},
            ],
        )

        assert result.success
        assert "A --> B" in result.output
        assert "B -.-> C" in result.output
        assert "C ==> D" in result.output

    @pytest.mark.asyncio
    async def test_class_diagram(self, tool):
        """Test class diagram generation."""
        result = await tool.execute(
            diagram_type="class",
            classes=[
                {
                    "name": "User",
                    "attributes": ["+id: int", "+name: str"],
                    "methods": ["+validate()", "+save()"],
                    "parent": "BaseModel",
                },
                {
                    "name": "Order",
                    "attributes": ["+id: int", "+user_id: int"],
                    "methods": ["+submit()"],
                },
            ],
            title="User Model",
        )

        assert result.success
        assert "classDiagram" in result.output
        assert "class User" in result.output
        assert "+id: int" in result.output
        assert "+validate()" in result.output
        assert "BaseModel <|-- User" in result.output

    @pytest.mark.asyncio
    async def test_er_diagram(self, tool):
        """Test ER diagram generation."""
        result = await tool.execute(
            diagram_type="er",
            entities=[
                {
                    "name": "User",
                    "columns": ["int id PK", "string email", "datetime created_at"],
                },
                {
                    "name": "Order",
                    "columns": ["int id PK", "int user_id FK", "decimal total"],
                },
            ],
            relationships=[
                {"from": "User", "to": "Order", "type": "one-to-many", "label": "places"},
            ],
            title="E-Commerce Schema",
        )

        assert result.success
        assert "erDiagram" in result.output
        assert "User {" in result.output
        assert "int id PK" in result.output
        assert "||--o{" in result.output  # one-to-many relationship

    @pytest.mark.asyncio
    async def test_er_diagram_with_dict_columns(self, tool):
        """Test ER diagram with dict-style column definitions."""
        result = await tool.execute(
            diagram_type="er",
            entities=[
                {
                    "name": "Product",
                    "columns": [
                        {"name": "id", "type": "int", "pk": True},
                        {"name": "name", "type": "string"},
                        {"name": "price", "type": "decimal"},
                    ],
                },
            ],
        )

        assert result.success
        assert "int id PK" in result.output
        assert "string name" in result.output

    @pytest.mark.asyncio
    async def test_state_diagram(self, tool):
        """Test state diagram generation."""
        result = await tool.execute(
            diagram_type="state",
            states=[
                {"id": "Idle", "label": "Waiting for input"},
                {"id": "Processing"},
                {"id": "Complete"},
            ],
            transitions=[
                {"from": "[*]", "to": "Idle"},
                {"from": "Idle", "to": "Processing", "trigger": "start"},
                {"from": "Processing", "to": "Complete", "trigger": "done"},
                {"from": "Complete", "to": "[*]"},
            ],
            title="Job States",
        )

        assert result.success
        assert "stateDiagram-v2" in result.output
        assert "Idle : Waiting for input" in result.output
        assert "--> Processing : start" in result.output

    @pytest.mark.asyncio
    async def test_gantt_diagram(self, tool):
        """Test Gantt chart generation."""
        result = await tool.execute(
            diagram_type="gantt",
            title="Project Timeline",
        )

        assert result.success
        assert "gantt" in result.output
        assert "title Project Timeline" in result.output
        assert "dateFormat" in result.output

    @pytest.mark.asyncio
    async def test_mindmap_diagram(self, tool):
        """Test mindmap generation."""
        result = await tool.execute(
            diagram_type="mindmap",
            title="Ideas",
        )

        assert result.success
        assert "mindmap" in result.output
        assert "root((Ideas))" in result.output

    @pytest.mark.asyncio
    async def test_output_to_file(self, tool):
        """Test saving diagram to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "diagram.md"

            result = await tool.execute(
                diagram_type="flowchart",
                nodes=[{"id": "A", "label": "Start"}],
                output_file=str(output_file),
            )

            assert result.success
            assert output_file.exists()
            content = output_file.read_text()
            assert "flowchart" in content

    @pytest.mark.asyncio
    async def test_metadata(self, tool):
        """Test that metadata is correctly set."""
        result = await tool.execute(
            diagram_type="sequence",
        )

        assert result.success
        assert result.metadata["diagram_type"] == "sequence"
        assert result.metadata["format"] == "mermaid"

    @pytest.mark.asyncio
    async def test_unsupported_diagram_type(self, tool):
        """Test handling of unsupported diagram type."""
        result = await tool.execute(
            diagram_type="unsupported_type",
        )

        assert not result.success
        assert "Unsupported diagram type" in result.error


# ═══════════════════════════════════════════════════════════════════════════════
# GeneratePlantUMLTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratePlantUMLTool:
    """Test suite for PlantUML diagram generation."""

    @pytest.fixture
    def tool(self):
        return GeneratePlantUMLTool()

    @pytest.mark.asyncio
    async def test_sequence_diagram(self, tool):
        """Test PlantUML sequence diagram."""
        result = await tool.execute(
            diagram_type="sequence",
            participants=["Client", "Server"],
            messages=[
                {"from": "Client", "to": "Server", "message": "Request"},
                {"from": "Server", "to": "Client", "message": "Response", "type": "reply"},
            ],
            title="API Call",
        )

        assert result.success
        assert "@startuml" in result.output
        assert "@enduml" in result.output
        assert "title API Call" in result.output
        assert "participant" in result.output

    @pytest.mark.asyncio
    async def test_sequence_with_theme(self, tool):
        """Test PlantUML sequence diagram with theme."""
        result = await tool.execute(
            diagram_type="sequence",
            theme="blueprint",
        )

        assert result.success
        assert "!theme blueprint" in result.output

    @pytest.mark.asyncio
    async def test_class_diagram(self, tool):
        """Test PlantUML class diagram."""
        result = await tool.execute(
            diagram_type="class",
            classes=[
                {
                    "name": "Animal",
                    "attributes": ["+name: string"],
                    "methods": ["+speak()"],
                    "stereotype": "abstract",
                },
                {
                    "name": "Dog",
                    "attributes": ["+breed: string"],
                    "methods": ["+bark()"],
                    "parent": "Animal",
                },
            ],
            title="Animal Hierarchy",
        )

        assert result.success
        assert "@startuml" in result.output
        assert "class Animal <<abstract>>" in result.output
        assert "Animal <|-- Dog" in result.output

    @pytest.mark.asyncio
    async def test_component_diagram(self, tool):
        """Test PlantUML component diagram."""
        result = await tool.execute(
            diagram_type="component",
            components=[
                {
                    "name": "WebServer",
                    "interfaces": ["HTTP"],
                    "dependencies": ["Database"],
                },
                {"name": "Database"},
            ],
            title="System Components",
        )

        assert result.success
        assert "component [WebServer]" in result.output
        assert "interface HTTP" in result.output
        assert "[WebServer] --> [Database]" in result.output

    @pytest.mark.asyncio
    async def test_usecase_diagram(self, tool):
        """Test PlantUML use case diagram."""
        result = await tool.execute(
            diagram_type="usecase",
            actors=["User", "Admin"],
            usecases=[
                {"name": "Login", "actor": "User"},
                {"name": "Manage Users", "actor": "Admin"},
            ],
            title="System Use Cases",
        )

        assert result.success
        assert "actor User" in result.output
        assert "actor Admin" in result.output
        assert 'usecase "Login"' in result.output

    @pytest.mark.asyncio
    async def test_deployment_diagram(self, tool):
        """Test PlantUML deployment diagram."""
        result = await tool.execute(
            diagram_type="deployment",
            nodes=[
                {
                    "name": "AWS",
                    "type": "cloud",
                    "components": ["EC2", "RDS"],
                },
                {
                    "name": "PostgreSQL",
                    "type": "database",
                    "components": ["Users", "Orders"],
                },
            ],
            title="Deployment Architecture",
        )

        assert result.success
        assert "cloud AWS" in result.output
        assert "database PostgreSQL" in result.output
        assert "[EC2]" in result.output

    @pytest.mark.asyncio
    async def test_activity_diagram(self, tool):
        """Test PlantUML activity diagram."""
        result = await tool.execute(
            diagram_type="activity",
            title="Workflow",
        )

        assert result.success
        assert "start" in result.output
        assert "stop" in result.output
        assert "if (condition?)" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateD2Tool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateD2Tool:
    """Test suite for D2 diagram generation."""

    @pytest.fixture
    def tool(self):
        return GenerateD2Tool()

    @pytest.mark.asyncio
    async def test_basic_nodes_and_edges(self, tool):
        """Test basic D2 diagram with nodes and edges."""
        result = await tool.execute(
            nodes=[
                {"id": "api", "label": "API Server"},
                {"id": "db", "label": "Database"},
            ],
            edges=[
                {"from": "api", "to": "db", "label": "SQL"},
            ],
            title="Simple Architecture",
        )

        assert result.success
        assert "title: Simple Architecture" in result.output
        assert "api: API Server" in result.output
        assert "db: Database" in result.output
        assert "api -> db: SQL" in result.output

    @pytest.mark.asyncio
    async def test_direction(self, tool):
        """Test D2 diagram with different directions."""
        result = await tool.execute(
            direction="down",
        )

        assert result.success
        assert "direction: down" in result.output

    @pytest.mark.asyncio
    async def test_containers(self, tool):
        """Test D2 diagram with containers."""
        result = await tool.execute(
            containers=[
                {
                    "id": "backend",
                    "label": "Backend Services",
                    "children": ["api", "worker", "scheduler"],
                },
            ],
        )

        assert result.success
        assert "backend: Backend Services {" in result.output
        assert "api" in result.output

    @pytest.mark.asyncio
    async def test_node_with_shape(self, tool):
        """Test D2 nodes with custom shapes."""
        result = await tool.execute(
            nodes=[
                {"id": "user", "label": "User", "shape": "person"},
                {"id": "db", "label": "Database", "shape": "cylinder"},
            ],
        )

        assert result.success
        assert "shape: person" in result.output
        assert "shape: cylinder" in result.output

    @pytest.mark.asyncio
    async def test_node_with_icon(self, tool):
        """Test D2 nodes with icons."""
        result = await tool.execute(
            nodes=[
                {"id": "aws", "label": "AWS", "icon": "https://icons.terrastruct.com/aws/compute/ec2.svg"},
            ],
        )

        assert result.success
        assert "icon:" in result.output

    @pytest.mark.asyncio
    async def test_theme(self, tool):
        """Test D2 diagram with theme."""
        result = await tool.execute(
            theme="1",
        )

        assert result.success
        assert "theme-id: 1" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# DiagramFromCodeTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiagramFromCodeTool:
    """Test suite for code-to-diagram extraction."""

    @pytest.fixture
    def tool(self):
        return DiagramFromCodeTool()

    @pytest.fixture
    def sample_python_code(self, tmp_path):
        """Create a sample Python file for testing."""
        code = '''
class BaseModel:
    """Base model class."""

    def save(self):
        pass

    def delete(self):
        pass


class User(BaseModel):
    """User model."""

    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
        self._password = None

    def validate(self) -> bool:
        return "@" in self.email

    def set_password(self, password: str):
        self._password = password


class Order(BaseModel):
    """Order model."""

    def __init__(self, user_id: int, total: float):
        self.user_id = user_id
        self.total = total

    def submit(self):
        pass
'''
        file_path = tmp_path / "models.py"
        file_path.write_text(code)
        return file_path

    @pytest.fixture
    def sample_project(self, tmp_path):
        """Create a sample project structure."""
        # Create directories
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "models").mkdir()
        (tmp_path / "src" / "services").mkdir()

        # Create files
        (tmp_path / "src" / "models" / "user.py").write_text('''
class User:
    pass
''')
        (tmp_path / "src" / "models" / "order.py").write_text('''
from .user import User

class Order:
    pass
''')
        (tmp_path / "src" / "services" / "auth.py").write_text('''
from ..models.user import User

class AuthService:
    def login(self, user: User):
        pass
''')
        return tmp_path

    @pytest.mark.asyncio
    async def test_class_diagram_from_file(self, tool, sample_python_code):
        """Test class diagram extraction from Python file."""
        result = await tool.execute(
            diagram_type="class",
            file_path=str(sample_python_code),
            format="mermaid",
        )

        assert result.success
        assert "classDiagram" in result.output
        assert "class User" in result.output
        assert "class Order" in result.output
        assert "class BaseModel" in result.output
        assert "BaseModel <|-- User" in result.output

    @pytest.mark.asyncio
    async def test_class_diagram_with_private(self, tool, sample_python_code):
        """Test class diagram including private members."""
        result = await tool.execute(
            diagram_type="class",
            file_path=str(sample_python_code),
            include_private=True,
            format="mermaid",
        )

        assert result.success
        # Private method should be included
        assert "set_password" in result.output

    @pytest.mark.asyncio
    async def test_class_diagram_plantuml_format(self, tool, sample_python_code):
        """Test class diagram in PlantUML format."""
        result = await tool.execute(
            diagram_type="class",
            file_path=str(sample_python_code),
            format="plantuml",
        )

        assert result.success
        assert "@startuml" in result.output
        assert "@enduml" in result.output
        assert "class User" in result.output

    @pytest.mark.asyncio
    async def test_class_diagram_d2_format(self, tool, sample_python_code):
        """Test class diagram in D2 format."""
        result = await tool.execute(
            diagram_type="class",
            file_path=str(sample_python_code),
            format="d2",
        )

        assert result.success
        assert "User" in result.output
        assert "shape: class" in result.output

    @pytest.mark.asyncio
    async def test_architecture_diagram(self, tool, sample_project):
        """Test architecture diagram from project structure."""
        result = await tool.execute(
            diagram_type="architecture",
            path=str(sample_project / "src"),
            format="mermaid",
        )

        assert result.success
        assert "flowchart TB" in result.output
        assert "subgraph models" in result.output
        assert "subgraph services" in result.output

    @pytest.mark.asyncio
    async def test_dependencies_diagram(self, tool, sample_project):
        """Test dependency diagram from project."""
        result = await tool.execute(
            diagram_type="dependencies",
            path=str(sample_project / "src"),
            format="mermaid",
        )

        assert result.success
        assert "flowchart LR" in result.output

    @pytest.mark.asyncio
    async def test_call_graph(self, tool, sample_python_code):
        """Test call graph generation."""
        result = await tool.execute(
            diagram_type="call_graph",
            file_path=str(sample_python_code),
            format="mermaid",
        )

        assert result.success
        assert "flowchart LR" in result.output

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test handling of non-existent file."""
        result = await tool.execute(
            diagram_type="class",
            file_path="/nonexistent/path/file.py",
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_requires_path_or_file(self, tool):
        """Test that either path or file_path must be provided."""
        result = await tool.execute(
            diagram_type="class",
        )

        assert not result.success
        assert "must be provided" in result.error

    @pytest.mark.asyncio
    async def test_metadata_files_analyzed(self, tool, sample_project):
        """Test that metadata includes files analyzed count."""
        result = await tool.execute(
            diagram_type="class",
            path=str(sample_project / "src"),
            format="mermaid",
        )

        assert result.success
        assert "files_analyzed" in result.metadata
        assert result.metadata["files_analyzed"] >= 3


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateSequenceDiagramTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateSequenceDiagramTool:
    """Test suite for specialized sequence diagram generation."""

    @pytest.fixture
    def tool(self):
        return GenerateSequenceDiagramTool()

    @pytest.mark.asyncio
    async def test_mermaid_format(self, tool):
        """Test Mermaid sequence diagram."""
        result = await tool.execute(
            participants=["Browser", "API", "DB"],
            steps=[
                {"from": "Browser", "to": "API", "action": "POST /login", "response": "200 OK"},
                {"from": "API", "to": "DB", "action": "SELECT user", "response": "user data"},
            ],
            format="mermaid",
            title="Login Flow",
        )

        assert result.success
        assert "sequenceDiagram" in result.output
        assert "participant Browser" in result.output
        assert "POST /login" in result.output
        assert "200 OK" in result.output

    @pytest.mark.asyncio
    async def test_plantuml_format(self, tool):
        """Test PlantUML sequence diagram."""
        result = await tool.execute(
            participants=["Client", "Server"],
            steps=[
                {"from": "Client", "to": "Server", "action": "Request"},
            ],
            format="plantuml",
        )

        assert result.success
        assert "@startuml" in result.output
        assert "@enduml" in result.output

    @pytest.mark.asyncio
    async def test_autonumber(self, tool):
        """Test sequence diagram with autonumbering."""
        result = await tool.execute(
            participants=["A", "B"],
            steps=[
                {"from": "A", "to": "B", "action": "Step 1"},
                {"from": "B", "to": "A", "action": "Step 2"},
            ],
            autonumber=True,
            format="mermaid",
        )

        assert result.success
        assert "autonumber" in result.output

    @pytest.mark.asyncio
    async def test_async_calls(self, tool):
        """Test sequence diagram with async calls."""
        result = await tool.execute(
            steps=[
                {"from": "A", "to": "B", "action": "Async call", "async": True},
            ],
            format="mermaid",
        )

        assert result.success
        assert "-->>>" in result.output

    @pytest.mark.asyncio
    async def test_no_responses(self, tool):
        """Test sequence diagram without response arrows."""
        result = await tool.execute(
            steps=[
                {"from": "A", "to": "B", "action": "Call", "response": "Response"},
            ],
            show_responses=False,
            format="mermaid",
        )

        assert result.success
        # Response should not appear when show_responses is False
        assert result.output.count("->>>") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# GenerateERDiagramTool Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateERDiagramTool:
    """Test suite for ER diagram generation."""

    @pytest.fixture
    def tool(self):
        return GenerateERDiagramTool()

    @pytest.fixture
    def sample_sqlalchemy_models(self, tmp_path):
        """Create sample SQLAlchemy model file."""
        code = '''
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    email = Column(String(255))
    name = Column(String(100))
    created_at = Column(DateTime)

    orders = relationship("Order", back_populates="user")


class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    total = Column(Integer)

    user = relationship("User", back_populates="orders")
'''
        file_path = tmp_path / "models.py"
        file_path.write_text(code)
        return file_path

    @pytest.fixture
    def sample_sql_schema(self, tmp_path):
        """Create sample SQL schema file."""
        sql = '''
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255),
    name VARCHAR(100),
    created_at TIMESTAMP
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    total DECIMAL(10, 2),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200),
    price DECIMAL(10, 2)
);
'''
        file_path = tmp_path / "schema.sql"
        file_path.write_text(sql)
        return file_path

    @pytest.mark.asyncio
    async def test_from_tables_list(self, tool):
        """Test ER diagram from table definitions."""
        result = await tool.execute(
            tables=[
                {
                    "name": "users",
                    "columns": ["id int PK", "email string", "name string"],
                },
                {
                    "name": "orders",
                    "columns": ["id int PK", "user_id int FK", "total decimal"],
                    "foreign_keys": ["user_id -> users.id"],
                },
            ],
            format="mermaid",
            title="E-Commerce",
        )

        assert result.success
        assert "erDiagram" in result.output
        assert "users {" in result.output
        assert "int id PK" in result.output

    @pytest.mark.asyncio
    async def test_from_sqlalchemy(self, tool, sample_sqlalchemy_models):
        """Test ER diagram extraction from SQLAlchemy models."""
        result = await tool.execute(
            file_path=str(sample_sqlalchemy_models),
            format="mermaid",
        )

        assert result.success
        assert "erDiagram" in result.output
        assert "User {" in result.output
        assert "Order {" in result.output

    @pytest.mark.asyncio
    async def test_from_sql(self, tool, sample_sql_schema):
        """Test ER diagram extraction from SQL file."""
        result = await tool.execute(
            sql_file=str(sample_sql_schema),
            format="mermaid",
        )

        assert result.success
        assert "erDiagram" in result.output
        assert "users {" in result.output
        assert "orders {" in result.output
        assert "products {" in result.output

    @pytest.mark.asyncio
    async def test_plantuml_format(self, tool):
        """Test ER diagram in PlantUML format."""
        result = await tool.execute(
            tables=[
                {"name": "users", "columns": ["id int PK", "name string"]},
            ],
            format="plantuml",
        )

        assert result.success
        assert "@startuml" in result.output
        assert "entity users" in result.output

    @pytest.mark.asyncio
    async def test_d2_format(self, tool):
        """Test ER diagram in D2 format."""
        result = await tool.execute(
            tables=[
                {"name": "users", "columns": ["id int PK", "name string"]},
            ],
            format="d2",
        )

        assert result.success
        assert "users:" in result.output
        assert "shape: sql_table" in result.output

    @pytest.mark.asyncio
    async def test_hide_types(self, tool):
        """Test ER diagram without column types."""
        result = await tool.execute(
            tables=[
                {"name": "users", "columns": ["id int PK", "name string"]},
            ],
            show_types=False,
            format="mermaid",
        )

        assert result.success
        # With show_types=False, types are replaced with 'string'
        assert "string id PK" in result.output

    @pytest.mark.asyncio
    async def test_no_tables_error(self, tool):
        """Test error when no tables provided or found."""
        result = await tool.execute(
            format="mermaid",
        )

        assert not result.success
        assert "No tables" in result.error

    @pytest.mark.asyncio
    async def test_metadata_tables_count(self, tool, sample_sql_schema):
        """Test that metadata includes table count."""
        result = await tool.execute(
            sql_file=str(sample_sql_schema),
            format="mermaid",
        )

        assert result.success
        assert "tables_count" in result.metadata
        assert result.metadata["tables_count"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiagramToolsIntegration:
    """Integration tests for diagram tools."""

    @pytest.mark.asyncio
    async def test_tools_registered(self):
        """Test that all diagram tools are registered in the registry."""
        from sindri.tools.registry import ToolRegistry

        registry = ToolRegistry.default()

        assert registry.get_tool("generate_mermaid") is not None
        assert registry.get_tool("generate_plantuml") is not None
        assert registry.get_tool("generate_d2") is not None
        assert registry.get_tool("diagram_from_code") is not None
        assert registry.get_tool("generate_sequence_diagram") is not None
        assert registry.get_tool("generate_er_diagram") is not None

    @pytest.mark.asyncio
    async def test_skuld_agent_exists(self):
        """Test that Skuld agent is defined in the registry."""
        from sindri.agents.registry import AGENTS, get_agent

        assert "skuld" in AGENTS

        skuld = get_agent("skuld")
        assert skuld.name == "skuld"
        assert "diagram" in skuld.role.lower()
        assert "generate_mermaid" in skuld.tools
        assert "generate_plantuml" in skuld.tools
        assert "generate_d2" in skuld.tools

    @pytest.mark.asyncio
    async def test_brokkr_can_delegate_to_skuld(self):
        """Test that Brokkr can delegate to Skuld."""
        from sindri.agents.registry import get_agent

        brokkr = get_agent("brokkr")
        assert "skuld" in brokkr.delegate_to
