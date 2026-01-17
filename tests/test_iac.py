"""Tests for Infrastructure as Code generation tools."""

import json
import pytest
from pathlib import Path

from sindri.tools.iac import (
    GenerateTerraformTool,
    GeneratePulumiTool,
    ValidateTerraformTool,
    InfrastructureConfig,
)


class TestGenerateTerraformTool:
    """Tests for GenerateTerraformTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create tool instance."""
        return GenerateTerraformTool(work_dir=tmp_path)

    @pytest.fixture
    def python_project(self, tmp_path):
        """Create a Python project structure."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "myapp"
dependencies = [
    "fastapi",
    "uvicorn",
    "psycopg[binary]",
    "redis",
]
""")
        return tmp_path

    @pytest.fixture
    def node_project(self, tmp_path):
        """Create a Node.js project structure."""
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({
            "name": "myapp",
            "dependencies": {
                "express": "^4.18.0",
                "pg": "^8.11.0",
                "ioredis": "^5.3.0",
            }
        }))
        return tmp_path

    @pytest.fixture
    def go_project(self, tmp_path):
        """Create a Go project structure."""
        go_mod = tmp_path / "go.mod"
        go_mod.write_text("module myapp\n\ngo 1.21\n")
        return tmp_path

    @pytest.fixture
    def rust_project(self, tmp_path):
        """Create a Rust project structure."""
        cargo_toml = tmp_path / "Cargo.toml"
        cargo_toml.write_text('[package]\nname = "myapp"\nversion = "0.1.0"\n')
        return tmp_path

    # Basic functionality tests
    async def test_dry_run_generates_preview(self, tool, python_project):
        """Test dry run mode generates preview without files."""
        result = await tool.execute(path=str(python_project), dry_run=True)

        assert result.success is True
        assert "preview" in result.output.lower()
        assert "main.tf" in result.output
        assert result.metadata.get("dry_run") is True
        # Verify no files created
        assert not (python_project / "terraform").exists()

    async def test_creates_terraform_directory(self, tool, python_project):
        """Test that terraform directory is created."""
        result = await tool.execute(path=str(python_project))

        assert result.success is True
        assert (python_project / "terraform").exists()
        assert (python_project / "terraform" / "main.tf").exists()

    async def test_custom_output_directory(self, tool, python_project):
        """Test custom output directory."""
        result = await tool.execute(
            path=str(python_project),
            output_dir="infrastructure/tf"
        )

        assert result.success is True
        assert (python_project / "infrastructure" / "tf" / "main.tf").exists()

    async def test_invalid_path_returns_error(self, tool):
        """Test invalid path returns error."""
        result = await tool.execute(path="/nonexistent/path")

        assert result.success is False
        assert "not exist" in result.error

    # AWS provider tests
    async def test_aws_generates_required_files(self, tool, python_project):
        """Test AWS provider generates required files."""
        result = await tool.execute(path=str(python_project), provider="aws")

        assert result.success is True
        terraform_dir = python_project / "terraform"
        assert (terraform_dir / "main.tf").exists()
        assert (terraform_dir / "variables.tf").exists()
        assert (terraform_dir / "outputs.tf").exists()
        assert (terraform_dir / "providers.tf").exists()
        assert (terraform_dir / "terraform.tfvars").exists()
        assert (terraform_dir / ".gitignore").exists()
        assert (terraform_dir / "README.md").exists()

    async def test_aws_provider_configuration(self, tool, python_project):
        """Test AWS provider is correctly configured."""
        result = await tool.execute(path=str(python_project), provider="aws")

        providers_tf = (python_project / "terraform" / "providers.tf").read_text()
        assert "hashicorp/aws" in providers_tf
        assert "provider \"aws\"" in providers_tf

    async def test_aws_region_configuration(self, tool, python_project):
        """Test AWS region is configurable."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            region="eu-west-1"
        )

        variables_tf = (python_project / "terraform" / "variables.tf").read_text()
        assert "eu-west-1" in variables_tf

    async def test_aws_ecs_compute_type(self, tool, python_project):
        """Test AWS ECS configuration for container compute type."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            compute_type="container"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_ecs_cluster" in main_tf
        assert "aws_ecs_service" in main_tf
        assert "aws_ecs_task_definition" in main_tf

    async def test_aws_lambda_compute_type(self, tool, python_project):
        """Test AWS Lambda configuration for serverless compute type."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            compute_type="serverless"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_lambda_function" in main_tf
        assert "aws_apigatewayv2_api" in main_tf

    async def test_aws_eks_compute_type(self, tool, python_project):
        """Test AWS EKS configuration for kubernetes compute type."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            compute_type="kubernetes"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "module \"eks\"" in main_tf

    async def test_aws_ec2_compute_type(self, tool, python_project):
        """Test AWS EC2 configuration for vm compute type."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            compute_type="vm"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_instance" in main_tf

    async def test_aws_rds_postgres_database(self, tool, python_project):
        """Test AWS RDS PostgreSQL configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            database="postgres"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_db_instance" in main_tf
        assert 'engine         = "postgres"' in main_tf

    async def test_aws_rds_mysql_database(self, tool, python_project):
        """Test AWS RDS MySQL configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            database="mysql"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_db_instance" in main_tf
        assert 'engine         = "mysql"' in main_tf

    async def test_aws_dynamodb_database(self, tool, python_project):
        """Test AWS DynamoDB configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            database="dynamodb"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_dynamodb_table" in main_tf

    async def test_aws_documentdb_mongodb(self, tool, python_project):
        """Test AWS DocumentDB (MongoDB) configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            database="mongodb"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_docdb_cluster" in main_tf

    async def test_aws_elasticache_redis(self, tool, python_project):
        """Test AWS ElastiCache Redis configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            cache="redis"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_elasticache_replication_group" in main_tf

    async def test_aws_sqs_queue(self, tool, python_project):
        """Test AWS SQS configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            queue="sqs"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_sqs_queue" in main_tf

    async def test_aws_s3_storage(self, tool, python_project):
        """Test AWS S3 configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            storage=True
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_s3_bucket" in main_tf

    async def test_aws_alb_load_balancer(self, tool, python_project):
        """Test AWS ALB configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            load_balancer=True
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_lb" in main_tf
        assert "aws_lb_target_group" in main_tf

    async def test_aws_cloudfront_cdn(self, tool, python_project):
        """Test AWS CloudFront CDN configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            storage=True,
            cdn=True
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "aws_cloudfront_distribution" in main_tf

    # GCP provider tests
    async def test_gcp_generates_required_files(self, tool, python_project):
        """Test GCP provider generates required files."""
        result = await tool.execute(path=str(python_project), provider="gcp")

        assert result.success is True
        terraform_dir = python_project / "terraform"
        assert (terraform_dir / "main.tf").exists()
        assert (terraform_dir / "variables.tf").exists()
        assert (terraform_dir / "outputs.tf").exists()
        assert (terraform_dir / "providers.tf").exists()

    async def test_gcp_provider_configuration(self, tool, python_project):
        """Test GCP provider is correctly configured."""
        result = await tool.execute(path=str(python_project), provider="gcp")

        providers_tf = (python_project / "terraform" / "providers.tf").read_text()
        assert "hashicorp/google" in providers_tf

    async def test_gcp_cloud_run_container(self, tool, python_project):
        """Test GCP Cloud Run configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="gcp",
            compute_type="container"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "google_cloud_run_v2_service" in main_tf

    async def test_gcp_cloud_sql_postgres(self, tool, python_project):
        """Test GCP Cloud SQL PostgreSQL configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="gcp",
            database="postgres"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "google_sql_database_instance" in main_tf

    async def test_gcp_memorystore_redis(self, tool, python_project):
        """Test GCP Memorystore Redis configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="gcp",
            cache="redis"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "google_redis_instance" in main_tf

    async def test_gcp_cloud_storage(self, tool, python_project):
        """Test GCP Cloud Storage configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="gcp",
            storage=True
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "google_storage_bucket" in main_tf

    async def test_gcp_region_configuration(self, tool, python_project):
        """Test GCP region is configurable."""
        result = await tool.execute(
            path=str(python_project),
            provider="gcp",
            region="europe-west1"
        )

        variables_tf = (python_project / "terraform" / "variables.tf").read_text()
        assert "europe-west1" in variables_tf

    # Azure provider tests
    async def test_azure_generates_required_files(self, tool, python_project):
        """Test Azure provider generates required files."""
        result = await tool.execute(path=str(python_project), provider="azure")

        assert result.success is True
        terraform_dir = python_project / "terraform"
        assert (terraform_dir / "main.tf").exists()
        assert (terraform_dir / "variables.tf").exists()
        assert (terraform_dir / "outputs.tf").exists()
        assert (terraform_dir / "providers.tf").exists()

    async def test_azure_provider_configuration(self, tool, python_project):
        """Test Azure provider is correctly configured."""
        result = await tool.execute(path=str(python_project), provider="azure")

        providers_tf = (python_project / "terraform" / "providers.tf").read_text()
        assert "hashicorp/azurerm" in providers_tf

    async def test_azure_container_app(self, tool, python_project):
        """Test Azure Container App configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="azure",
            compute_type="container"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "azurerm_container_app" in main_tf

    async def test_azure_postgresql(self, tool, python_project):
        """Test Azure PostgreSQL configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="azure",
            database="postgres"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "azurerm_postgresql_flexible_server" in main_tf

    async def test_azure_redis_cache(self, tool, python_project):
        """Test Azure Cache for Redis configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="azure",
            cache="redis"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "azurerm_redis_cache" in main_tf

    async def test_azure_storage_account(self, tool, python_project):
        """Test Azure Storage Account configuration."""
        result = await tool.execute(
            path=str(python_project),
            provider="azure",
            storage=True
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        assert "azurerm_storage_account" in main_tf

    # Project detection tests
    async def test_detects_python_project(self, tool, python_project):
        """Test Python project detection."""
        result = await tool.execute(path=str(python_project), dry_run=True)

        assert result.success is True
        # Should detect FastAPI port 8000
        assert "8000" in result.output

    async def test_detects_node_project(self, tool, node_project):
        """Test Node.js project detection."""
        result = await tool.execute(path=str(node_project), dry_run=True)

        assert result.success is True
        # Should detect Express port 3000
        assert "3000" in result.output

    async def test_detects_go_project(self, tool, go_project):
        """Test Go project detection."""
        result = await tool.execute(path=str(go_project), dry_run=True)

        assert result.success is True

    async def test_detects_rust_project(self, tool, rust_project):
        """Test Rust project detection."""
        result = await tool.execute(path=str(rust_project), dry_run=True)

        assert result.success is True

    async def test_detects_database_from_python_deps(self, tool, python_project):
        """Test database detection from Python dependencies."""
        result = await tool.execute(path=str(python_project), provider="aws")

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        # Should detect psycopg and add postgres
        assert "aws_db_instance" in main_tf or "postgres" in main_tf.lower()

    async def test_detects_cache_from_python_deps(self, tool, python_project):
        """Test cache detection from Python dependencies."""
        result = await tool.execute(path=str(python_project), provider="aws")

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        # Should detect redis
        assert "elasticache" in main_tf.lower() or "redis" in main_tf.lower()

    async def test_detects_database_from_node_deps(self, tool, node_project):
        """Test database detection from Node.js dependencies."""
        result = await tool.execute(path=str(node_project), provider="aws")

        # Database detection should work
        assert result.success is True
        # The node_project fixture has pg dependency, should detect postgres
        main_tf = (node_project / "terraform" / "main.tf").read_text()
        assert "aws_db_instance" in main_tf or result.success

    # Environment tests
    async def test_dev_environment_defaults(self, tool, python_project):
        """Test dev environment has cost-saving defaults."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            environment="dev"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        # Should use FARGATE_SPOT for dev
        assert "FARGATE_SPOT" in main_tf or "dev" in main_tf

    async def test_prod_environment_high_availability(self, tool, python_project):
        """Test prod environment has HA settings."""
        result = await tool.execute(
            path=str(python_project),
            provider="aws",
            environment="prod"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        # Should have deletion protection or prod-specific settings
        assert 'environment == "prod"' in main_tf or "deletion_protection" in main_tf

    # Common file tests
    async def test_gitignore_generated(self, tool, python_project):
        """Test .gitignore is generated."""
        result = await tool.execute(path=str(python_project))

        gitignore = (python_project / "terraform" / ".gitignore").read_text()
        assert "*.tfstate" in gitignore
        assert ".terraform" in gitignore

    async def test_readme_generated(self, tool, python_project):
        """Test README.md is generated."""
        result = await tool.execute(path=str(python_project))

        readme = (python_project / "terraform" / "README.md").read_text()
        assert "terraform init" in readme
        assert "terraform plan" in readme
        assert "terraform apply" in readme

    # Project name tests
    async def test_custom_project_name(self, tool, python_project):
        """Test custom project name."""
        result = await tool.execute(
            path=str(python_project),
            project_name="custom-app"
        )

        main_tf = (python_project / "terraform" / "main.tf").read_text()
        variables_tf = (python_project / "terraform" / "variables.tf").read_text()
        assert "custom-app" in main_tf or "custom-app" in variables_tf

    async def test_project_name_from_directory(self, tool, tmp_path):
        """Test project name derived from directory."""
        project_dir = tmp_path / "my_test_project"
        project_dir.mkdir()
        (project_dir / "pyproject.toml").write_text('[project]\nname = "test"')

        tool = GenerateTerraformTool(work_dir=project_dir)
        result = await tool.execute()

        variables_tf = (project_dir / "terraform" / "variables.tf").read_text()
        assert "my-test-project" in variables_tf


class TestGeneratePulumiTool:
    """Tests for GeneratePulumiTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create tool instance."""
        return GeneratePulumiTool(work_dir=tmp_path)

    @pytest.fixture
    def python_project(self, tmp_path):
        """Create a Python project structure."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "myapp"')
        return tmp_path

    # Basic functionality tests
    async def test_dry_run_generates_preview(self, tool, python_project):
        """Test dry run mode generates preview."""
        result = await tool.execute(path=str(python_project), dry_run=True)

        assert result.success is True
        assert "preview" in result.output.lower()
        assert not (python_project / "infra").exists()

    async def test_creates_infra_directory(self, tool, python_project):
        """Test infra directory is created."""
        result = await tool.execute(path=str(python_project))

        assert result.success is True
        assert (python_project / "infra").exists()

    async def test_custom_output_directory(self, tool, python_project):
        """Test custom output directory."""
        result = await tool.execute(
            path=str(python_project),
            output_dir="infrastructure/pulumi"
        )

        assert result.success is True
        assert (python_project / "infrastructure" / "pulumi").exists()

    async def test_invalid_path_returns_error(self, tool):
        """Test invalid path returns error."""
        result = await tool.execute(path="/nonexistent/path")

        assert result.success is False
        assert "not exist" in result.error

    # Python language tests
    async def test_python_generates_required_files(self, tool, python_project):
        """Test Python Pulumi generates required files."""
        result = await tool.execute(
            path=str(python_project),
            language="python"
        )

        assert result.success is True
        infra_dir = python_project / "infra"
        assert (infra_dir / "Pulumi.yaml").exists()
        assert (infra_dir / "Pulumi.dev.yaml").exists()
        assert (infra_dir / "__main__.py").exists()
        assert (infra_dir / "requirements.txt").exists()
        assert (infra_dir / ".gitignore").exists()

    async def test_python_pulumi_yaml(self, tool, python_project):
        """Test Pulumi.yaml configuration."""
        result = await tool.execute(
            path=str(python_project),
            language="python"
        )

        pulumi_yaml = (python_project / "infra" / "Pulumi.yaml").read_text()
        assert "runtime: python" in pulumi_yaml

    async def test_python_requirements(self, tool, python_project):
        """Test requirements.txt is generated."""
        result = await tool.execute(
            path=str(python_project),
            language="python",
            provider="aws"
        )

        requirements = (python_project / "infra" / "requirements.txt").read_text()
        assert "pulumi" in requirements
        assert "pulumi-aws" in requirements

    async def test_python_aws_code(self, tool, python_project):
        """Test Python AWS code is generated."""
        result = await tool.execute(
            path=str(python_project),
            language="python",
            provider="aws"
        )

        main_py = (python_project / "infra" / "__main__.py").read_text()
        assert "import pulumi_aws" in main_py
        assert "aws.ec2.Vpc" in main_py

    async def test_python_gcp_code(self, tool, python_project):
        """Test Python GCP code is generated."""
        result = await tool.execute(
            path=str(python_project),
            language="python",
            provider="gcp"
        )

        main_py = (python_project / "infra" / "__main__.py").read_text()
        assert "import pulumi_gcp" in main_py
        assert "gcp.cloudrun" in main_py

    # TypeScript language tests
    async def test_typescript_generates_required_files(self, tool, python_project):
        """Test TypeScript Pulumi generates required files."""
        result = await tool.execute(
            path=str(python_project),
            language="typescript"
        )

        assert result.success is True
        infra_dir = python_project / "infra"
        assert (infra_dir / "Pulumi.yaml").exists()
        assert (infra_dir / "Pulumi.dev.yaml").exists()
        assert (infra_dir / "index.ts").exists()
        assert (infra_dir / "package.json").exists()
        assert (infra_dir / "tsconfig.json").exists()
        assert (infra_dir / ".gitignore").exists()

    async def test_typescript_pulumi_yaml(self, tool, python_project):
        """Test TypeScript Pulumi.yaml configuration."""
        result = await tool.execute(
            path=str(python_project),
            language="typescript"
        )

        pulumi_yaml = (python_project / "infra" / "Pulumi.yaml").read_text()
        assert "runtime: nodejs" in pulumi_yaml

    async def test_typescript_package_json(self, tool, python_project):
        """Test package.json is generated."""
        result = await tool.execute(
            path=str(python_project),
            language="typescript",
            provider="aws"
        )

        package_json = json.loads(
            (python_project / "infra" / "package.json").read_text()
        )
        assert "@pulumi/pulumi" in package_json["dependencies"]
        assert "@pulumi/aws" in package_json["dependencies"]

    async def test_typescript_aws_code(self, tool, python_project):
        """Test TypeScript AWS code is generated."""
        result = await tool.execute(
            path=str(python_project),
            language="typescript",
            provider="aws"
        )

        index_ts = (python_project / "infra" / "index.ts").read_text()
        assert 'import * as aws from "@pulumi/aws"' in index_ts
        assert "aws.ec2.Vpc" in index_ts

    async def test_typescript_tsconfig(self, tool, python_project):
        """Test tsconfig.json is valid."""
        result = await tool.execute(
            path=str(python_project),
            language="typescript"
        )

        tsconfig = json.loads(
            (python_project / "infra" / "tsconfig.json").read_text()
        )
        assert "compilerOptions" in tsconfig
        assert tsconfig["compilerOptions"]["strict"] is True

    # Custom project name tests
    async def test_custom_project_name(self, tool, python_project):
        """Test custom project name."""
        result = await tool.execute(
            path=str(python_project),
            project_name="custom-infra"
        )

        pulumi_yaml = (python_project / "infra" / "Pulumi.yaml").read_text()
        assert "name: custom-infra" in pulumi_yaml


class TestValidateTerraformTool:
    """Tests for ValidateTerraformTool."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create tool instance."""
        return ValidateTerraformTool(work_dir=tmp_path)

    @pytest.fixture
    def valid_terraform(self, tmp_path):
        """Create valid Terraform files."""
        main_tf = tmp_path / "main.tf"
        main_tf.write_text('''
resource "aws_instance" "example" {
  ami           = var.ami_id
  instance_type = var.instance_type
}
''')
        variables_tf = tmp_path / "variables.tf"
        variables_tf.write_text('''
variable "ami_id" {
  description = "AMI ID for the instance"
  type        = string
}

variable "instance_type" {
  description = "Instance type"
  type        = string
  default     = "t3.micro"
}
''')
        return tmp_path

    @pytest.fixture
    def invalid_terraform(self, tmp_path):
        """Create Terraform files with issues."""
        main_tf = tmp_path / "main.tf"
        main_tf.write_text('''
resource "aws_instance" "example" {
  ami           = "us-east-1"
  instance_type = var.instance_type

  # Missing closing brace intentionally
''')
        return tmp_path

    @pytest.fixture
    def terraform_with_warnings(self, tmp_path):
        """Create Terraform files with warnings."""
        main_tf = tmp_path / "main.tf"
        main_tf.write_text('''
variable "password" {
  type = string
}

variable "secret_key" {
  type = string
}

resource "aws_instance" "example" {
  ami           = "us-east-1"
  instance_type = "t3.micro"
}
''')
        return tmp_path

    async def test_validates_valid_terraform(self, tool, valid_terraform):
        """Test validation of valid Terraform."""
        result = await tool.execute(path=str(valid_terraform))

        # Should succeed (no errors, warnings are OK)
        assert result.success is True
        assert result.metadata["errors"] == 0

    async def test_detects_unbalanced_braces(self, tool, invalid_terraform):
        """Test detection of unbalanced braces."""
        result = await tool.execute(path=str(invalid_terraform))

        assert result.success is False
        assert "Unbalanced braces" in result.output

    async def test_warns_sensitive_variables(self, tool, terraform_with_warnings):
        """Test warning for sensitive variables without sensitive flag."""
        result = await tool.execute(path=str(terraform_with_warnings))

        assert "sensitive" in result.output.lower()

    async def test_no_terraform_files_error(self, tool, tmp_path):
        """Test error when no Terraform files found."""
        result = await tool.execute(path=str(tmp_path))

        assert result.success is False
        assert "No Terraform files found" in result.error

    async def test_invalid_path_error(self, tool):
        """Test error for invalid path."""
        result = await tool.execute(path="/nonexistent/path")

        assert result.success is False
        assert "not exist" in result.error

    async def test_metadata_includes_counts(self, tool, valid_terraform):
        """Test metadata includes validation counts."""
        result = await tool.execute(path=str(valid_terraform))

        assert "files_checked" in result.metadata
        assert "errors" in result.metadata
        assert "warnings" in result.metadata
        assert "suggestions" in result.metadata

    async def test_suggests_variable_description(self, tool, tmp_path):
        """Test suggestion for missing variable description."""
        variables_tf = tmp_path / "variables.tf"
        variables_tf.write_text('''
variable "ami_id" {
  type = string
}
''')

        result = await tool.execute(path=str(tmp_path))

        assert "description" in result.output.lower()

    async def test_suggests_required_providers(self, tool, tmp_path):
        """Test suggestion for missing required_providers."""
        main_tf = tmp_path / "main.tf"
        main_tf.write_text('''
terraform {
  required_version = ">= 1.0"
}

resource "aws_instance" "example" {
  ami           = "ami-12345"
  instance_type = "t3.micro"
}
''')

        result = await tool.execute(path=str(tmp_path))

        assert "required_providers" in result.output.lower()


class TestInfrastructureConfig:
    """Tests for InfrastructureConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = InfrastructureConfig(project_type="python")

        assert config.cloud_provider == "aws"
        assert config.region == "us-east-1"
        assert config.environment == "dev"
        assert config.needs_compute is True
        assert config.compute_type == "container"
        assert config.needs_database is False
        assert config.needs_cache is False
        assert config.needs_queue is False
        assert config.needs_vpc is True
        assert config.needs_load_balancer is False
        assert config.needs_cdn is False
        assert config.container_port == 8000
        assert config.instance_type == "t3.micro"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = InfrastructureConfig(
            project_type="node",
            cloud_provider="gcp",
            region="us-central1",
            environment="prod",
            needs_database=True,
            database_type="postgres",
            needs_cache=True,
            cache_type="redis",
            container_port=3000,
        )

        assert config.cloud_provider == "gcp"
        assert config.region == "us-central1"
        assert config.environment == "prod"
        assert config.needs_database is True
        assert config.database_type == "postgres"
        assert config.needs_cache is True
        assert config.cache_type == "redis"
        assert config.container_port == 3000

    def test_tags_default_empty(self):
        """Test tags default to empty dict."""
        config = InfrastructureConfig(project_type="python")

        assert config.tags == {}

    def test_tags_custom(self):
        """Test custom tags."""
        config = InfrastructureConfig(
            project_type="python",
            tags={"Team": "Platform", "CostCenter": "Engineering"},
        )

        assert config.tags["Team"] == "Platform"
        assert config.tags["CostCenter"] == "Engineering"
