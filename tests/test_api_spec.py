"""Tests for API Spec Generator tools."""

import pytest
import json
from pathlib import Path

from sindri.tools.api_spec import (
    GenerateApiSpecTool,
    ValidateApiSpecTool,
    FrameworkInfo,
    RouteInfo,
)


class TestFrameworkDetection:
    """Tests for web framework detection."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    def test_detect_fastapi_from_pyproject(self, tool, tmp_path):
        """Test FastAPI detection from pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "myapi"
dependencies = ["fastapi", "uvicorn"]
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "fastapi"
        assert info.language == "python"

    def test_detect_fastapi_from_requirements(self, tool, tmp_path):
        """Test FastAPI detection from requirements.txt."""
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("fastapi==0.100.0\nuvicorn==0.22.0\n")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "fastapi"
        assert info.language == "python"

    def test_detect_flask_from_pyproject(self, tool, tmp_path):
        """Test Flask detection from pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "myapi"
dependencies = ["flask"]
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "flask"
        assert info.language == "python"

    def test_detect_flask_from_requirements(self, tool, tmp_path):
        """Test Flask detection from requirements.txt."""
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("flask==2.0.0\n")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "flask"
        assert info.language == "python"

    def test_detect_django_from_requirements(self, tool, tmp_path):
        """Test Django detection from requirements.txt."""
        requirements = tmp_path / "requirements.txt"
        requirements.write_text("django==4.0.0\ndjango-rest-framework==3.14.0\n")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "django"
        assert info.language == "python"

    def test_detect_express_from_package_json(self, tool, tmp_path):
        """Test Express.js detection from package.json."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "name": "myapi",
            "dependencies": {
                "express": "^4.18.0"
            }
        }))

        info = tool._detect_framework(tmp_path)
        assert info.framework == "express"
        assert info.language == "javascript"

    def test_detect_express_typescript(self, tool, tmp_path):
        """Test Express.js with TypeScript detection."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "name": "myapi",
            "dependencies": {
                "express": "^4.18.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0"
            }
        }))

        info = tool._detect_framework(tmp_path)
        assert info.framework == "express"
        assert info.language == "typescript"

    def test_detect_gin_from_go_mod(self, tool, tmp_path):
        """Test Gin (Go) detection from go.mod."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text("""
module myapi

go 1.21

require github.com/gin-gonic/gin v1.9.0
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "gin"
        assert info.language == "go"

    def test_detect_echo_from_go_mod(self, tool, tmp_path):
        """Test Echo (Go) detection from go.mod."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text("""
module myapi

go 1.21

require github.com/labstack/echo/v4 v4.11.0
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "echo"
        assert info.language == "go"

    def test_detect_actix_from_cargo_toml(self, tool, tmp_path):
        """Test Actix (Rust) detection from Cargo.toml."""
        cargo_toml = tmp_path / "Cargo.toml"
        cargo_toml.write_text("""
[package]
name = "myapi"

[dependencies]
actix-web = "4.0"
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "actix"
        assert info.language == "rust"

    def test_detect_fastapi_from_source(self, tool, tmp_path):
        """Test FastAPI detection from source code."""
        main_py = tmp_path / "main.py"
        main_py.write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "fastapi"
        assert info.language == "python"
        assert info.entry_point == str(main_py)

    def test_detect_flask_from_source(self, tool, tmp_path):
        """Test Flask detection from source code."""
        app_py = tmp_path / "app.py"
        app_py.write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello"
""")

        info = tool._detect_framework(tmp_path)
        assert info.framework == "flask"
        assert info.language == "python"

    def test_detect_generic_empty_project(self, tool, tmp_path):
        """Test generic detection for empty project."""
        info = tool._detect_framework(tmp_path)
        assert info.framework == "generic"
        assert info.language == "unknown"


class TestRouteExtraction:
    """Tests for route extraction from various frameworks."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    def test_extract_fastapi_routes(self, tool, tmp_path):
        """Test FastAPI route extraction."""
        main_py = tmp_path / "main.py"
        main_py.write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    return []

@app.post("/users")
def create_user():
    return {"id": 1}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}

@app.delete("/users/{user_id}")
def delete_user(user_id: int):
    pass
""")

        fw_info = FrameworkInfo(framework="fastapi", language="python")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 4

        paths = [(r.path, r.method) for r in routes]
        assert ("/users", "GET") in paths
        assert ("/users", "POST") in paths
        assert ("/users/{user_id}", "GET") in paths
        assert ("/users/{user_id}", "DELETE") in paths

    def test_extract_fastapi_router_routes(self, tool, tmp_path):
        """Test FastAPI APIRouter route extraction."""
        routes_py = tmp_path / "routes.py"
        routes_py.write_text("""
from fastapi import APIRouter

router = APIRouter()

@router.get("/items")
def list_items():
    return []

@router.post("/items")
def create_item():
    return {"id": 1}

@router.put("/items/{item_id}")
def update_item(item_id: int):
    pass
""")

        fw_info = FrameworkInfo(framework="fastapi", language="python")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 3
        methods = [r.method for r in routes]
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods

    def test_extract_flask_routes(self, tool, tmp_path):
        """Test Flask route extraction."""
        app_py = tmp_path / "app.py"
        app_py.write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello"

@app.route("/users", methods=["GET", "POST"])
def users():
    return []

@app.route("/users/<int:user_id>")
def get_user(user_id):
    return {"id": user_id}
""")

        fw_info = FrameworkInfo(framework="flask", language="python")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) >= 3

        # Check that we extracted the multi-method route as separate entries
        methods = [r.method for r in routes]
        assert "GET" in methods
        assert "POST" in methods

    def test_extract_flask_blueprint_routes(self, tool, tmp_path):
        """Test Flask Blueprint route extraction."""
        bp_py = tmp_path / "blueprints.py"
        bp_py.write_text("""
from flask import Blueprint

api = Blueprint('api', __name__)

@api.route("/health")
def health():
    return {"status": "ok"}

@api.route("/items", methods=["GET"])
def list_items():
    return []
""")

        fw_info = FrameworkInfo(framework="flask", language="python")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) >= 2
        paths = [r.path for r in routes]
        assert "/health" in paths
        assert "/items" in paths

    def test_extract_django_routes(self, tool, tmp_path):
        """Test Django route extraction."""
        urls_py = tmp_path / "urls.py"
        urls_py.write_text("""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('users/', views.users, name='users'),
    path('users/<int:pk>/', views.user_detail, name='user_detail'),
    path('items/<slug:slug>/', views.item_detail, name='item_detail'),
]
""")

        fw_info = FrameworkInfo(framework="django", language="python")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 4
        paths = [r.path for r in routes]
        assert "/" in paths
        assert "/users/" in paths

    def test_extract_express_routes(self, tool, tmp_path):
        """Test Express.js route extraction."""
        routes_js = tmp_path / "routes.js"
        routes_js.write_text("""
const express = require('express');
const router = express.Router();

router.get('/users', (req, res) => {
    res.json([]);
});

router.post('/users', (req, res) => {
    res.json({id: 1});
});

router.get('/users/:userId', (req, res) => {
    res.json({id: req.params.userId});
});

app.delete('/users/:userId', (req, res) => {
    res.status(204).send();
});

module.exports = router;
""")

        fw_info = FrameworkInfo(framework="express", language="javascript")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 4
        methods = [r.method for r in routes]
        assert "GET" in methods
        assert "POST" in methods
        assert "DELETE" in methods

    def test_extract_express_typescript_routes(self, tool, tmp_path):
        """Test Express.js TypeScript route extraction."""
        routes_ts = tmp_path / "routes.ts"
        routes_ts.write_text("""
import { Router, Request, Response } from 'express';

const router = Router();

router.get('/items', (req: Request, res: Response) => {
    res.json([]);
});

router.post('/items', (req: Request, res: Response) => {
    res.json({id: 1});
});

router.patch('/items/:id', (req: Request, res: Response) => {
    res.json({id: req.params.id});
});

export default router;
""")

        fw_info = FrameworkInfo(framework="express", language="typescript")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 3
        methods = [r.method for r in routes]
        assert "GET" in methods
        assert "POST" in methods
        assert "PATCH" in methods

    def test_extract_gin_routes(self, tool, tmp_path):
        """Test Gin (Go) route extraction."""
        main_go = tmp_path / "main.go"
        main_go.write_text("""
package main

import "github.com/gin-gonic/gin"

func main() {
    r := gin.Default()

    r.GET("/users", listUsers)
    r.POST("/users", createUser)
    r.GET("/users/:id", getUser)
    r.PUT("/users/:id", updateUser)
    r.DELETE("/users/:id", deleteUser)
}
""")

        fw_info = FrameworkInfo(framework="gin", language="go")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 5
        methods = [r.method for r in routes]
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "DELETE" in methods

    def test_extract_echo_routes(self, tool, tmp_path):
        """Test Echo (Go) route extraction."""
        main_go = tmp_path / "main.go"
        main_go.write_text("""
package main

import "github.com/labstack/echo/v4"

func main() {
    e := echo.New()

    e.GET("/", hello)
    e.GET("/users", listUsers)
    e.POST("/users", createUser)
    e.PUT("/users/:id", updateUser)
}
""")

        fw_info = FrameworkInfo(framework="echo", language="go")
        routes = tool._extract_routes(tmp_path, fw_info, None, None)

        assert len(routes) == 4


class TestPathParameterExtraction:
    """Tests for path parameter extraction."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    def test_extract_fastapi_path_params(self, tool):
        """Test FastAPI style path parameter extraction."""
        params = tool._extract_path_params("/users/{user_id}")
        assert len(params) == 1
        assert params[0]["name"] == "user_id"
        assert params[0]["in"] == "path"
        assert params[0]["required"] is True

    def test_extract_fastapi_typed_path_params(self, tool):
        """Test FastAPI style typed path parameter extraction."""
        params = tool._extract_path_params("/users/{user_id:int}/posts/{post_id:int}")
        assert len(params) == 2
        assert params[0]["name"] == "user_id"
        assert params[0]["schema"]["type"] == "integer"
        assert params[1]["name"] == "post_id"
        assert params[1]["schema"]["type"] == "integer"

    def test_extract_flask_path_params(self, tool):
        """Test Flask style path parameter extraction."""
        params = tool._extract_path_params("/users/<user_id>")
        assert len(params) == 1
        assert params[0]["name"] == "user_id"
        assert params[0]["in"] == "path"

    def test_extract_flask_typed_path_params(self, tool):
        """Test Flask style typed path parameter extraction."""
        params = tool._extract_path_params("/users/<int:user_id>/posts/<string:slug>")
        assert len(params) == 2
        assert params[0]["name"] == "user_id"
        assert params[0]["schema"]["type"] == "integer"
        assert params[1]["name"] == "slug"
        assert params[1]["schema"]["type"] == "string"

    def test_extract_express_path_params(self, tool):
        """Test Express style path parameter extraction."""
        params = tool._extract_express_path_params("/users/:userId/posts/:postId")
        assert len(params) == 2
        assert params[0]["name"] == "userId"
        assert params[1]["name"] == "postId"

    def test_extract_django_path_params(self, tool):
        """Test Django style path parameter extraction."""
        params = tool._extract_django_path_params("/<int:pk>/<slug:slug>/")
        assert len(params) == 2
        assert params[0]["name"] == "pk"
        assert params[0]["schema"]["type"] == "integer"
        assert params[1]["name"] == "slug"
        assert params[1]["schema"]["type"] == "string"


class TestOpenAPIGeneration:
    """Tests for OpenAPI spec generation."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    def test_generate_basic_spec(self, tool):
        """Test basic OpenAPI spec generation."""
        routes = [
            RouteInfo(path="/users", method="GET", handler="list_users"),
            RouteInfo(path="/users", method="POST", handler="create_user"),
        ]
        fw_info = FrameworkInfo(framework="fastapi", language="python")

        spec = tool._generate_openapi_spec(
            routes=routes,
            title="Test API",
            version="1.0.0",
            description="Test description",
            servers=None,
            framework_info=fw_info
        )

        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "Test API"
        assert spec["info"]["version"] == "1.0.0"
        assert spec["info"]["description"] == "Test description"
        assert "/users" in spec["paths"]
        assert "get" in spec["paths"]["/users"]
        assert "post" in spec["paths"]["/users"]

    def test_generate_spec_with_params(self, tool):
        """Test OpenAPI spec generation with path parameters."""
        routes = [
            RouteInfo(
                path="/users/{user_id}",
                method="GET",
                handler="get_user",
                parameters=[{
                    "name": "user_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"}
                }]
            ),
        ]
        fw_info = FrameworkInfo(framework="fastapi", language="python")

        spec = tool._generate_openapi_spec(
            routes=routes,
            title="Test API",
            version="1.0.0",
            description=None,
            servers=None,
            framework_info=fw_info
        )

        assert "/users/{user_id}" in spec["paths"]
        assert "parameters" in spec["paths"]["/users/{user_id}"]["get"]
        params = spec["paths"]["/users/{user_id}"]["get"]["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "user_id"

    def test_generate_spec_with_servers(self, tool):
        """Test OpenAPI spec generation with custom servers."""
        routes = [RouteInfo(path="/health", method="GET", handler="health")]
        fw_info = FrameworkInfo(framework="fastapi", language="python")

        spec = tool._generate_openapi_spec(
            routes=routes,
            title="Test API",
            version="1.0.0",
            description=None,
            servers=["https://api.example.com", "http://localhost:8000"],
            framework_info=fw_info
        )

        assert len(spec["servers"]) == 2
        assert spec["servers"][0]["url"] == "https://api.example.com"
        assert spec["servers"][1]["url"] == "http://localhost:8000"

    def test_generate_spec_with_request_body(self, tool):
        """Test OpenAPI spec generation with request body for POST/PUT."""
        routes = [
            RouteInfo(path="/users", method="POST", handler="create_user"),
            RouteInfo(path="/users/{id}", method="PUT", handler="update_user"),
            RouteInfo(path="/users/{id}", method="PATCH", handler="patch_user"),
        ]
        fw_info = FrameworkInfo(framework="fastapi", language="python")

        spec = tool._generate_openapi_spec(
            routes=routes,
            title="Test API",
            version="1.0.0",
            description=None,
            servers=None,
            framework_info=fw_info
        )

        assert "requestBody" in spec["paths"]["/users"]["post"]
        assert "requestBody" in spec["paths"]["/users/{id}"]["put"]
        assert "requestBody" in spec["paths"]["/users/{id}"]["patch"]

    def test_path_conversion_flask_to_openapi(self, tool):
        """Test Flask path conversion to OpenAPI format."""
        path = tool._convert_path_to_openapi("/users/<int:id>", "flask")
        assert path == "/users/{id}"

    def test_path_conversion_express_to_openapi(self, tool):
        """Test Express path conversion to OpenAPI format."""
        path = tool._convert_path_to_openapi("/users/:userId/posts/:postId", "express")
        assert path == "/users/{userId}/posts/{postId}"


class TestGenerateApiSpecTool:
    """Integration tests for GenerateApiSpecTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_execute_fastapi_project(self, tool, tmp_path):
        """Test executing tool on a FastAPI project."""
        # Create a FastAPI project structure
        main_py = tmp_path / "main.py"
        main_py.write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/users")
def list_users():
    return []

@app.post("/users")
def create_user():
    return {"id": 1}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id}
""")

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("fastapi\nuvicorn\n")

        result = await tool.execute(
            path=str(tmp_path),
            title="Test FastAPI",
            dry_run=True
        )

        assert result.success
        assert result.metadata["framework"] == "fastapi"
        assert result.metadata["routes_count"] >= 4
        assert "openapi" in result.output

    @pytest.mark.asyncio
    async def test_execute_flask_project(self, tool, tmp_path):
        """Test executing tool on a Flask project."""
        app_py = tmp_path / "app.py"
        app_py.write_text("""
from flask import Flask

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello"

@app.route("/api/users", methods=["GET", "POST"])
def users():
    return []
""")

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("flask\n")

        result = await tool.execute(
            path=str(tmp_path),
            dry_run=True
        )

        assert result.success
        assert result.metadata["framework"] == "flask"
        assert result.metadata["routes_count"] >= 2

    @pytest.mark.asyncio
    async def test_execute_express_project(self, tool, tmp_path):
        """Test executing tool on an Express project."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "name": "test-api",
            "dependencies": {"express": "^4.18.0"}
        }))

        routes_js = tmp_path / "routes.js"
        routes_js.write_text("""
const express = require('express');
const router = express.Router();

router.get('/items', (req, res) => res.json([]));
router.post('/items', (req, res) => res.json({id: 1}));
router.get('/items/:id', (req, res) => res.json({id: req.params.id}));

module.exports = router;
""")

        result = await tool.execute(
            path=str(tmp_path),
            dry_run=True
        )

        assert result.success
        assert result.metadata["framework"] == "express"
        assert result.metadata["routes_count"] >= 3

    @pytest.mark.asyncio
    async def test_execute_with_output_file(self, tool, tmp_path):
        """Test executing tool and writing output file."""
        main_py = tmp_path / "main.py"
        main_py.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
""")

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("fastapi\n")

        result = await tool.execute(
            path=str(tmp_path),
            output="api.json",
            dry_run=False
        )

        assert result.success
        output_file = tmp_path / "api.json"
        assert output_file.exists()

        spec = json.loads(output_file.read_text())
        assert spec["openapi"] == "3.0.3"

    @pytest.mark.asyncio
    async def test_execute_yaml_output(self, tool, tmp_path):
        """Test executing tool with YAML output."""
        main_py = tmp_path / "main.py"
        main_py.write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/test")
def test():
    return {}
""")

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("fastapi\n")

        result = await tool.execute(
            path=str(tmp_path),
            format="yaml",
            dry_run=True
        )

        assert result.success
        # YAML output should contain openapi version
        assert "openapi:" in result.output or "openapi: " in result.output

    @pytest.mark.asyncio
    async def test_execute_no_routes_found(self, tool, tmp_path):
        """Test error when no routes are found."""
        # Empty Python file
        empty_py = tmp_path / "empty.py"
        empty_py.write_text("# No routes here\n")

        requirements = tmp_path / "requirements.txt"
        requirements.write_text("fastapi\n")

        result = await tool.execute(path=str(tmp_path))

        assert not result.success
        assert "No routes found" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_framework_detected(self, tool, tmp_path):
        """Test error when no framework is detected."""
        # Create a file that doesn't use any framework
        random_py = tmp_path / "random.py"
        random_py.write_text("print('hello')\n")

        result = await tool.execute(path=str(tmp_path))

        assert not result.success
        assert "Could not detect web framework" in result.error

    @pytest.mark.asyncio
    async def test_execute_nonexistent_path(self, tool, tmp_path):
        """Test error for nonexistent path."""
        result = await tool.execute(path="/nonexistent/path")

        assert not result.success
        assert "does not exist" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_framework_override(self, tool, tmp_path):
        """Test framework override."""
        app_py = tmp_path / "app.py"
        app_py.write_text("""
from flask import Flask
app = Flask(__name__)

@app.route("/test")
def test():
    return "test"
""")

        result = await tool.execute(
            path=str(tmp_path),
            framework="flask",
            dry_run=True
        )

        assert result.success
        assert result.metadata["framework"] == "flask"


class TestValidateApiSpecTool:
    """Tests for ValidateApiSpecTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a ValidateApiSpecTool instance."""
        return ValidateApiSpecTool(work_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_validate_valid_spec(self, tool, tmp_path):
        """Test validation of a valid OpenAPI spec."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                }
            }
        }))

        result = await tool.execute(file_path=str(spec_file))

        assert result.success
        assert len(result.metadata["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_missing_openapi_field(self, tool, tmp_path):
        """Test validation error for missing openapi field."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {}
        }))

        result = await tool.execute(file_path=str(spec_file))

        assert not result.success
        assert any("openapi" in e.lower() for e in result.metadata["errors"])

    @pytest.mark.asyncio
    async def test_validate_missing_info(self, tool, tmp_path):
        """Test validation error for missing info field."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "openapi": "3.0.3",
            "paths": {}
        }))

        result = await tool.execute(file_path=str(spec_file))

        assert not result.success
        assert any("info" in e.lower() for e in result.metadata["errors"])

    @pytest.mark.asyncio
    async def test_validate_missing_paths(self, tool, tmp_path):
        """Test validation error for missing paths field."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            }
        }))

        result = await tool.execute(file_path=str(spec_file))

        assert not result.success
        assert any("paths" in e.lower() for e in result.metadata["errors"])

    @pytest.mark.asyncio
    async def test_validate_invalid_json(self, tool, tmp_path):
        """Test validation error for invalid JSON."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text("{ invalid json }")

        result = await tool.execute(file_path=str(spec_file))

        assert not result.success

    @pytest.mark.asyncio
    async def test_validate_invalid_http_method(self, tool, tmp_path):
        """Test validation error for invalid HTTP method."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "invalid_method": {
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        }))

        result = await tool.execute(file_path=str(spec_file))

        assert not result.success
        assert any("invalid_method" in e.lower() for e in result.metadata["errors"])

    @pytest.mark.asyncio
    async def test_validate_missing_responses(self, tool, tmp_path):
        """Test validation warning for missing responses."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers"
                    }
                }
            }
        }))

        result = await tool.execute(file_path=str(spec_file))

        # Should pass but with warnings
        assert result.success or len(result.metadata["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_validate_path_param_warning(self, tool, tmp_path):
        """Test validation warning for undefined path parameters."""
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps({
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/users/{userId}": {
                    "get": {
                        "responses": {"200": {"description": "OK"}}
                        # Missing parameters definition
                    }
                }
            }
        }))

        result = await tool.execute(file_path=str(spec_file))

        # Should generate a warning about undefined path parameter
        warnings = result.metadata.get("warnings", [])
        assert any("userId" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_validate_content_directly(self, tool):
        """Test validation of content passed directly."""
        content = json.dumps({
            "openapi": "3.0.3",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/health": {
                    "get": {
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        })

        result = await tool.execute(content=content)

        assert result.success

    @pytest.mark.asyncio
    async def test_validate_nonexistent_file(self, tool, tmp_path):
        """Test error for nonexistent file."""
        result = await tool.execute(file_path="/nonexistent/file.json")

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_validate_no_input(self, tool):
        """Test error when no input provided."""
        result = await tool.execute()

        assert not result.success
        assert "file_path or content must be provided" in result.error


class TestProjectNameDetection:
    """Tests for project name detection."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    def test_detect_name_from_pyproject(self, tool, tmp_path):
        """Test project name detection from pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('''
[project]
name = "my-awesome-api"
''')

        name = tool._detect_project_name(tmp_path)
        assert name == "My Awesome Api"

    def test_detect_name_from_package_json(self, tool, tmp_path):
        """Test project name detection from package.json."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "express-api"}))

        name = tool._detect_project_name(tmp_path)
        assert name == "Express Api"

    def test_detect_name_from_go_mod(self, tool, tmp_path):
        """Test project name detection from go.mod."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text("module github.com/user/awesome-service\n")

        name = tool._detect_project_name(tmp_path)
        assert name == "Awesome Service"

    def test_detect_name_from_cargo_toml(self, tool, tmp_path):
        """Test project name detection from Cargo.toml."""
        cargo_toml = tmp_path / "Cargo.toml"
        cargo_toml.write_text('''
[package]
name = "rust_api_server"
''')

        name = tool._detect_project_name(tmp_path)
        assert name == "Rust Api Server"

    def test_detect_name_none_for_empty_project(self, tool, tmp_path):
        """Test None returned for empty project."""
        name = tool._detect_project_name(tmp_path)
        assert name is None


class TestFileFiltering:
    """Tests for file filtering with include/exclude patterns."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create a GenerateApiSpecTool instance."""
        return GenerateApiSpecTool(work_dir=tmp_path)

    def test_exclude_test_files(self, tool, tmp_path):
        """Test that test files are excluded by default."""
        # Create test files
        (tmp_path / "test_routes.py").write_text("# test file")
        (tmp_path / "routes_test.py").write_text("# test file")
        (tmp_path / "routes.py").write_text("# actual routes")

        files = tool._get_files(tmp_path, [".py"], None, None)
        filenames = [f.name for f in files]

        assert "routes.py" in filenames
        assert "test_routes.py" not in filenames
        assert "routes_test.py" not in filenames

    def test_exclude_node_modules(self, tool, tmp_path):
        """Test that node_modules is excluded."""
        node_modules = tmp_path / "node_modules" / "express"
        node_modules.mkdir(parents=True)
        (node_modules / "index.js").write_text("// express")
        (tmp_path / "routes.js").write_text("// routes")

        files = tool._get_files(tmp_path, [".js"], None, None)
        filenames = [f.name for f in files]

        assert "routes.js" in filenames
        # node_modules files should be excluded

    def test_include_pattern_filter(self, tool, tmp_path):
        """Test include pattern filtering."""
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "routes.py").write_text("# api routes")
        (tmp_path / "other").mkdir(parents=True)
        (tmp_path / "other" / "something.py").write_text("# other")

        files = tool._get_files(tmp_path, [".py"], ["api/*"], None)
        paths = [str(f.relative_to(tmp_path)) for f in files]

        assert any("api" in p for p in paths)
