"""Infrastructure as Code generation tools for Sindri.

Provides tools for generating Terraform and Pulumi configurations
based on project detection and requirements.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import structlog

from sindri.tools.base import Tool, ToolResult

log = structlog.get_logger()


@dataclass
class InfrastructureConfig:
    """Detected infrastructure requirements."""

    project_type: str  # python, node, rust, go, generic
    cloud_provider: str = "aws"  # aws, gcp, azure
    region: str = "us-east-1"
    environment: str = "dev"

    # Compute
    needs_compute: bool = True
    compute_type: str = "container"  # container, vm, serverless, kubernetes

    # Database
    needs_database: bool = False
    database_type: Optional[str] = None  # postgres, mysql, mongodb, dynamodb, etc.

    # Storage
    needs_storage: bool = False
    storage_type: Optional[str] = None  # s3, gcs, blob

    # Cache
    needs_cache: bool = False
    cache_type: Optional[str] = None  # redis, memcached

    # Queue
    needs_queue: bool = False
    queue_type: Optional[str] = None  # sqs, pubsub, servicebus

    # Networking
    needs_vpc: bool = True
    needs_load_balancer: bool = False
    needs_cdn: bool = False

    # Additional settings
    container_port: int = 8000
    instance_type: str = "t3.micro"
    tags: dict = field(default_factory=dict)


class GenerateTerraformTool(Tool):
    """Generate Terraform configuration files.

    Creates Terraform HCL files based on project detection and
    specified infrastructure requirements.
    """

    name = "generate_terraform"
    description = """Generate Terraform configuration files for infrastructure.

Automatically detects project type and generates appropriate Terraform HCL
with support for AWS, GCP, and Azure.

Examples:
- generate_terraform() - Auto-detect and generate AWS Terraform
- generate_terraform(provider="gcp") - Generate for Google Cloud
- generate_terraform(provider="azure") - Generate for Azure
- generate_terraform(compute_type="serverless") - Use Lambda/Functions
- generate_terraform(compute_type="kubernetes") - Use EKS/GKE/AKS
- generate_terraform(database="postgres") - Include RDS/Cloud SQL
- generate_terraform(cache="redis") - Include ElastiCache/Memorystore
- generate_terraform(dry_run=true) - Preview without creating files"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for Terraform files (default: terraform/)",
            },
            "provider": {
                "type": "string",
                "description": "Cloud provider: 'aws', 'gcp', 'azure'",
                "enum": ["aws", "gcp", "azure"],
            },
            "region": {
                "type": "string",
                "description": "Cloud region (default: us-east-1 for AWS)",
            },
            "environment": {
                "type": "string",
                "description": "Environment name: 'dev', 'staging', 'prod'",
                "enum": ["dev", "staging", "prod"],
            },
            "compute_type": {
                "type": "string",
                "description": "Compute type: 'container', 'vm', 'serverless', 'kubernetes'",
                "enum": ["container", "vm", "serverless", "kubernetes"],
            },
            "database": {
                "type": "string",
                "description": "Database type: 'postgres', 'mysql', 'mongodb', 'dynamodb'",
            },
            "cache": {
                "type": "string",
                "description": "Cache type: 'redis', 'memcached'",
            },
            "queue": {
                "type": "string",
                "description": "Queue type: 'sqs', 'pubsub', 'servicebus', 'rabbitmq'",
            },
            "storage": {
                "type": "boolean",
                "description": "Include object storage (S3/GCS/Blob)",
            },
            "cdn": {
                "type": "boolean",
                "description": "Include CDN (CloudFront/Cloud CDN/Azure CDN)",
            },
            "load_balancer": {
                "type": "boolean",
                "description": "Include load balancer",
            },
            "project_name": {
                "type": "string",
                "description": "Project name for resource naming",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview Terraform without creating files",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        output_dir: Optional[str] = None,
        provider: str = "aws",
        region: Optional[str] = None,
        environment: str = "dev",
        compute_type: str = "container",
        database: Optional[str] = None,
        cache: Optional[str] = None,
        queue: Optional[str] = None,
        storage: bool = False,
        cdn: bool = False,
        load_balancer: bool = False,
        project_name: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate Terraform configuration files.

        Args:
            path: Project directory path
            output_dir: Output directory for Terraform files
            provider: Cloud provider (aws, gcp, azure)
            region: Cloud region
            environment: Environment (dev, staging, prod)
            compute_type: Type of compute (container, vm, serverless, kubernetes)
            database: Database type to include
            cache: Cache type to include
            queue: Queue type to include
            storage: Include object storage
            cdn: Include CDN
            load_balancer: Include load balancer
            project_name: Project name for naming
            dry_run: Preview without creating files
        """
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        # Detect project configuration
        config = self._detect_project(project_path)

        # Apply overrides
        config.cloud_provider = provider
        config.environment = environment
        config.compute_type = compute_type

        if region:
            config.region = region
        else:
            # Set default region based on provider
            config.region = {
                "aws": "us-east-1",
                "gcp": "us-central1",
                "azure": "eastus",
            }.get(provider, "us-east-1")

        if database:
            config.needs_database = True
            config.database_type = database
        if cache:
            config.needs_cache = True
            config.cache_type = cache
        if queue:
            config.needs_queue = True
            config.queue_type = queue
        if storage:
            config.needs_storage = True
            config.storage_type = {"aws": "s3", "gcp": "gcs", "azure": "blob"}.get(
                provider, "s3"
            )
        if cdn:
            config.needs_cdn = True
        if load_balancer:
            config.needs_load_balancer = True

        # Determine project name
        if not project_name:
            project_name = project_path.name.lower().replace("_", "-").replace(" ", "-")

        config.tags = {
            "Project": project_name,
            "Environment": environment,
            "ManagedBy": "Terraform",
            "GeneratedBy": "Sindri",
        }

        # Generate Terraform files
        files = self._generate_terraform(config, project_name)

        # Determine output directory
        output_path = project_path / (output_dir or "terraform")

        if dry_run:
            output = "Terraform configuration preview:\n\n"
            for filename, content in files.items():
                output += f"--- {filename} ---\n{content}\n\n"
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "dry_run": True,
                    "provider": provider,
                    "files": list(files.keys()),
                },
            )

        # Create output directory and write files
        try:
            output_path.mkdir(parents=True, exist_ok=True)

            for filename, content in files.items():
                (output_path / filename).write_text(content)

            log.info(
                "terraform_generated",
                provider=provider,
                output_dir=str(output_path),
                files=list(files.keys()),
            )

            return ToolResult(
                success=True,
                output=f"Generated Terraform configuration in {output_path}\n\n"
                + "Files created:\n"
                + "\n".join(f"  - {f}" for f in files.keys())
                + "\n\nNext steps:\n"
                + "  1. cd terraform/\n"
                + "  2. terraform init\n"
                + "  3. terraform plan\n"
                + "  4. terraform apply",
                metadata={
                    "provider": provider,
                    "output_dir": str(output_path),
                    "files": list(files.keys()),
                },
            )
        except Exception as e:
            log.error("terraform_write_failed", error=str(e))
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to write Terraform files: {str(e)}",
            )

    def _detect_project(self, path: Path) -> InfrastructureConfig:
        """Detect project type and infrastructure needs."""
        config = InfrastructureConfig(project_type="generic")

        # Detect project type and defaults
        if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
            config.project_type = "python"
            config.container_port = 8000

            # Check for frameworks
            content = ""
            if (path / "pyproject.toml").exists():
                content = (path / "pyproject.toml").read_text().lower()
            elif (path / "requirements.txt").exists():
                content = (path / "requirements.txt").read_text().lower()

            if "fastapi" in content or "uvicorn" in content:
                config.container_port = 8000
            elif "flask" in content:
                config.container_port = 5000
            elif "django" in content:
                config.container_port = 8000

            # Check for database needs
            if any(db in content for db in ["psycopg", "asyncpg", "sqlalchemy"]):
                config.needs_database = True
                config.database_type = "postgres"
            elif "pymongo" in content:
                config.needs_database = True
                config.database_type = "mongodb"
            elif "mysql" in content:
                config.needs_database = True
                config.database_type = "mysql"

            # Check for cache needs
            if "redis" in content or "celery" in content:
                config.needs_cache = True
                config.cache_type = "redis"

        elif (path / "package.json").exists():
            config.project_type = "node"
            config.container_port = 3000

            pkg_json = json.loads((path / "package.json").read_text())
            deps = {
                **pkg_json.get("dependencies", {}),
                **pkg_json.get("devDependencies", {}),
            }
            deps_str = " ".join(deps.keys()).lower()

            if "next" in deps:
                config.container_port = 3000
            elif "express" in deps:
                config.container_port = 3000

            if any(db in deps_str for db in ["pg", "postgres", "sequelize", "prisma"]):
                config.needs_database = True
                config.database_type = "postgres"
            elif "mongoose" in deps_str or "mongodb" in deps_str:
                config.needs_database = True
                config.database_type = "mongodb"

            if "redis" in deps_str or "ioredis" in deps_str or "bull" in deps_str:
                config.needs_cache = True
                config.cache_type = "redis"

        elif (path / "Cargo.toml").exists():
            config.project_type = "rust"
            config.container_port = 8080

        elif (path / "go.mod").exists():
            config.project_type = "go"
            config.container_port = 8080

        return config

    def _generate_terraform(
        self, config: InfrastructureConfig, project_name: str
    ) -> dict[str, str]:
        """Generate Terraform files based on configuration."""
        files = {}

        if config.cloud_provider == "aws":
            files = self._generate_aws_terraform(config, project_name)
        elif config.cloud_provider == "gcp":
            files = self._generate_gcp_terraform(config, project_name)
        elif config.cloud_provider == "azure":
            files = self._generate_azure_terraform(config, project_name)

        # Add common files
        files[".gitignore"] = self._terraform_gitignore()
        files["README.md"] = self._terraform_readme(config, project_name)

        return files

    def _generate_aws_terraform(
        self, config: InfrastructureConfig, project_name: str
    ) -> dict[str, str]:
        """Generate AWS Terraform configuration."""
        files = {}

        # Main configuration
        files["main.tf"] = self._aws_main_tf(config, project_name)

        # Variables
        files["variables.tf"] = self._aws_variables_tf(config, project_name)

        # Outputs
        files["outputs.tf"] = self._aws_outputs_tf(config)

        # terraform.tfvars
        files["terraform.tfvars"] = self._aws_tfvars(config, project_name)

        # Provider configuration
        files["providers.tf"] = f"""# AWS Provider Configuration
terraform {{
  required_version = ">= 1.0"

  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}

  # Uncomment to use remote state
  # backend "s3" {{
  #   bucket = "{project_name}-terraform-state"
  #   key    = "{config.environment}/terraform.tfstate"
  #   region = "{config.region}"
  # }}
}}

provider "aws" {{
  region = var.region

  default_tags {{
    tags = var.tags
  }}
}}
"""

        return files

    def _aws_main_tf(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS main.tf."""
        sections = []

        # Data sources
        sections.append("""# Data Sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}
""")

        # VPC (if needed)
        if config.needs_vpc:
            sections.append(f"""# VPC Configuration
module "vpc" {{
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${{var.project_name}}-vpc"
  cidr = var.vpc_cidr

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = [for i in range(3) : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i in range(3) : cidrsubnet(var.vpc_cidr, 4, i + 3)]

  enable_nat_gateway   = var.environment == "prod"
  single_nat_gateway   = var.environment != "prod"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = var.tags
}}
""")

        # Compute resources
        if config.compute_type == "container":
            sections.append(self._aws_ecs_config(config, project_name))
        elif config.compute_type == "serverless":
            sections.append(self._aws_lambda_config(config, project_name))
        elif config.compute_type == "kubernetes":
            sections.append(self._aws_eks_config(config, project_name))
        elif config.compute_type == "vm":
            sections.append(self._aws_ec2_config(config, project_name))

        # Database
        if config.needs_database:
            sections.append(self._aws_database_config(config, project_name))

        # Cache
        if config.needs_cache:
            sections.append(self._aws_cache_config(config, project_name))

        # Queue
        if config.needs_queue:
            sections.append(self._aws_queue_config(config, project_name))

        # Storage
        if config.needs_storage:
            sections.append(self._aws_storage_config(config, project_name))

        # Load Balancer
        if config.needs_load_balancer and config.compute_type not in [
            "serverless",
            "kubernetes",
        ]:
            sections.append(self._aws_alb_config(config, project_name))

        # CDN
        if config.needs_cdn:
            sections.append(self._aws_cdn_config(config, project_name))

        return "\n".join(sections)

    def _aws_ecs_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS ECS configuration."""
        return f"""# ECS Cluster
resource "aws_ecs_cluster" "main" {{
  name = "${{var.project_name}}-cluster"

  setting {{
    name  = "containerInsights"
    value = var.environment == "prod" ? "enabled" : "disabled"
  }}

  tags = var.tags
}}

resource "aws_ecs_cluster_capacity_providers" "main" {{
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {{
    base              = 1
    weight            = 100
    capacity_provider = var.environment == "prod" ? "FARGATE" : "FARGATE_SPOT"
  }}
}}

# ECS Task Definition
resource "aws_ecs_task_definition" "app" {{
  family                   = "${{var.project_name}}-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.container_cpu
  memory                   = var.container_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {{
      name      = "app"
      image     = var.container_image
      essential = true

      portMappings = [
        {{
          containerPort = var.container_port
          protocol      = "tcp"
        }}
      ]

      environment = [
        {{
          name  = "ENVIRONMENT"
          value = var.environment
        }}
      ]

      logConfiguration = {{
        logDriver = "awslogs"
        options = {{
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "ecs"
        }}
      }}

      healthCheck = {{
        command     = ["CMD-SHELL", "curl -f http://localhost:${{var.container_port}}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }}
    }}
  ])

  tags = var.tags
}}

# ECS Service
resource "aws_ecs_service" "app" {{
  name            = "${{var.project_name}}-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {{
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }}

  dynamic "load_balancer" {{
    for_each = var.enable_load_balancer ? [1] : []
    content {{
      target_group_arn = aws_lb_target_group.app[0].arn
      container_name   = "app"
      container_port   = var.container_port
    }}
  }}

  lifecycle {{
    ignore_changes = [desired_count]
  }}

  tags = var.tags
}}

# IAM Roles for ECS
resource "aws_iam_role" "ecs_execution" {{
  name = "${{var.project_name}}-ecs-execution"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {{
          Service = "ecs-tasks.amazonaws.com"
        }}
      }}
    ]
  }})

  tags = var.tags
}}

resource "aws_iam_role_policy_attachment" "ecs_execution" {{
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}}

resource "aws_iam_role" "ecs_task" {{
  name = "${{var.project_name}}-ecs-task"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {{
          Service = "ecs-tasks.amazonaws.com"
        }}
      }}
    ]
  }})

  tags = var.tags
}}

# Security Group for ECS
resource "aws_security_group" "ecs" {{
  name        = "${{var.project_name}}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = var.enable_load_balancer ? [aws_security_group.alb[0].id] : []
    cidr_blocks     = var.enable_load_balancer ? [] : ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = var.tags
}}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "app" {{
  name              = "/ecs/${{var.project_name}}"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = var.tags
}}
"""

    def _aws_lambda_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS Lambda configuration."""
        runtime_map = {
            "python": "python3.11",
            "node": "nodejs20.x",
            "go": "provided.al2023",
            "rust": "provided.al2023",
            "generic": "python3.11",
        }
        runtime = runtime_map.get(config.project_type, "python3.11")

        return f"""# Lambda Function
resource "aws_lambda_function" "app" {{
  function_name = "${{var.project_name}}-app"
  role          = aws_iam_role.lambda_execution.arn
  handler       = var.lambda_handler
  runtime       = "{runtime}"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {{
    variables = {{
      ENVIRONMENT = var.environment
    }}
  }}

  vpc_config {{
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }}

  tags = var.tags
}}

# Lambda IAM Role
resource "aws_iam_role" "lambda_execution" {{
  name = "${{var.project_name}}-lambda-execution"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {{
          Service = "lambda.amazonaws.com"
        }}
      }}
    ]
  }})

  tags = var.tags
}}

resource "aws_iam_role_policy_attachment" "lambda_basic" {{
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {{
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}}

# Security Group for Lambda
resource "aws_security_group" "lambda" {{
  name        = "${{var.project_name}}-lambda-sg"
  description = "Security group for Lambda function"
  vpc_id      = module.vpc.vpc_id

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = var.tags
}}

# API Gateway
resource "aws_apigatewayv2_api" "app" {{
  name          = "${{var.project_name}}-api"
  protocol_type = "HTTP"

  cors_configuration {{
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["*"]
  }}

  tags = var.tags
}}

resource "aws_apigatewayv2_stage" "app" {{
  api_id      = aws_apigatewayv2_api.app.id
  name        = var.environment
  auto_deploy = true

  access_log_settings {{
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({{
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    }})
  }}

  tags = var.tags
}}

resource "aws_apigatewayv2_integration" "app" {{
  api_id             = aws_apigatewayv2_api.app.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.app.invoke_arn
}}

resource "aws_apigatewayv2_route" "app" {{
  api_id    = aws_apigatewayv2_api.app.id
  route_key = "$default"
  target    = "integrations/${{aws_apigatewayv2_integration.app.id}}"
}}

resource "aws_lambda_permission" "api_gateway" {{
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${{aws_apigatewayv2_api.app.execution_arn}}/*/*"
}}

resource "aws_cloudwatch_log_group" "api_gateway" {{
  name              = "/aws/apigateway/${{var.project_name}}"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = var.tags
}}
"""

    def _aws_eks_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS EKS configuration."""
        return f"""# EKS Cluster
module "eks" {{
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = "${{var.project_name}}-eks"
  cluster_version = "1.28"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true

  eks_managed_node_groups = {{
    default = {{
      name           = "default"
      instance_types = [var.eks_instance_type]

      min_size     = var.environment == "prod" ? 2 : 1
      max_size     = var.environment == "prod" ? 10 : 3
      desired_size = var.environment == "prod" ? 2 : 1

      capacity_type = var.environment == "prod" ? "ON_DEMAND" : "SPOT"
    }}
  }}

  tags = var.tags
}}

# OIDC Provider for IRSA
data "tls_certificate" "eks" {{
  url = module.eks.cluster_oidc_issuer_url
}}
"""

    def _aws_ec2_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS EC2 configuration."""
        return f"""# EC2 Instance
resource "aws_instance" "app" {{
  ami           = data.aws_ami.amazon_linux.id
  instance_type = var.instance_type

  subnet_id                   = module.vpc.private_subnets[0]
  vpc_security_group_ids      = [aws_security_group.ec2.id]
  associate_public_ip_address = false

  iam_instance_profile = aws_iam_instance_profile.app.name

  user_data = base64encode(<<-EOF
    #!/bin/bash
    yum update -y
    yum install -y docker
    systemctl start docker
    systemctl enable docker
    EOF
  )

  root_block_device {{
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }}

  tags = merge(var.tags, {{
    Name = "${{var.project_name}}-app"
  }})
}}

data "aws_ami" "amazon_linux" {{
  most_recent = true
  owners      = ["amazon"]

  filter {{
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }}
}}

resource "aws_security_group" "ec2" {{
  name        = "${{var.project_name}}-ec2-sg"
  description = "Security group for EC2 instance"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }}

  ingress {{
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = var.tags
}}

resource "aws_iam_role" "app" {{
  name = "${{var.project_name}}-ec2-role"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {{
          Service = "ec2.amazonaws.com"
        }}
      }}
    ]
  }})

  tags = var.tags
}}

resource "aws_iam_instance_profile" "app" {{
  name = "${{var.project_name}}-ec2-profile"
  role = aws_iam_role.app.name
}}

resource "aws_iam_role_policy_attachment" "ssm" {{
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}}
"""

    def _aws_database_config(
        self, config: InfrastructureConfig, project_name: str
    ) -> str:
        """Generate AWS database configuration."""
        if config.database_type in ("postgres", "mysql"):
            engine = "postgres" if config.database_type == "postgres" else "mysql"
            engine_version = "15" if config.database_type == "postgres" else "8.0"
            port = 5432 if config.database_type == "postgres" else 3306

            return f"""# RDS Database
resource "aws_db_subnet_group" "main" {{
  name       = "${{var.project_name}}-db-subnet"
  subnet_ids = module.vpc.private_subnets

  tags = var.tags
}}

resource "aws_security_group" "rds" {{
  name        = "${{var.project_name}}-rds-sg"
  description = "Security group for RDS"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port       = {port}
    to_port         = {port}
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }}

  tags = var.tags
}}

resource "aws_db_instance" "main" {{
  identifier = "${{var.project_name}}-db"

  engine         = "{engine}"
  engine_version = "{engine_version}"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_encrypted     = true

  db_name  = replace(var.project_name, "-", "_")
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = var.environment == "prod" ? 7 : 1
  skip_final_snapshot     = var.environment != "prod"
  deletion_protection     = var.environment == "prod"

  performance_insights_enabled = var.environment == "prod"
  monitoring_interval          = var.environment == "prod" ? 60 : 0

  tags = var.tags
}}
"""
        elif config.database_type == "dynamodb":
            return f"""# DynamoDB Table
resource "aws_dynamodb_table" "main" {{
  name         = "${{var.project_name}}-table"
  billing_mode = var.environment == "prod" ? "PROVISIONED" : "PAY_PER_REQUEST"

  read_capacity  = var.environment == "prod" ? 5 : null
  write_capacity = var.environment == "prod" ? 5 : null

  hash_key  = "pk"
  range_key = "sk"

  attribute {{
    name = "pk"
    type = "S"
  }}

  attribute {{
    name = "sk"
    type = "S"
  }}

  point_in_time_recovery {{
    enabled = var.environment == "prod"
  }}

  tags = var.tags
}}
"""
        elif config.database_type == "mongodb":
            return f"""# DocumentDB (MongoDB-compatible)
resource "aws_docdb_cluster" "main" {{
  cluster_identifier      = "${{var.project_name}}-docdb"
  engine                  = "docdb"
  master_username         = var.db_username
  master_password         = var.db_password
  db_subnet_group_name    = aws_docdb_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.docdb.id]
  skip_final_snapshot     = var.environment != "prod"
  deletion_protection     = var.environment == "prod"

  tags = var.tags
}}

resource "aws_docdb_cluster_instance" "main" {{
  count              = var.environment == "prod" ? 2 : 1
  identifier         = "${{var.project_name}}-docdb-${{count.index}}"
  cluster_identifier = aws_docdb_cluster.main.id
  instance_class     = var.db_instance_class
}}

resource "aws_docdb_subnet_group" "main" {{
  name       = "${{var.project_name}}-docdb-subnet"
  subnet_ids = module.vpc.private_subnets

  tags = var.tags
}}

resource "aws_security_group" "docdb" {{
  name        = "${{var.project_name}}-docdb-sg"
  description = "Security group for DocumentDB"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port       = 27017
    to_port         = 27017
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }}

  tags = var.tags
}}
"""
        return ""

    def _aws_cache_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS ElastiCache configuration."""
        engine = config.cache_type or "redis"

        return f"""# ElastiCache
resource "aws_elasticache_subnet_group" "main" {{
  name       = "${{var.project_name}}-cache-subnet"
  subnet_ids = module.vpc.private_subnets

  tags = var.tags
}}

resource "aws_security_group" "cache" {{
  name        = "${{var.project_name}}-cache-sg"
  description = "Security group for ElastiCache"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }}

  tags = var.tags
}}

resource "aws_elasticache_replication_group" "main" {{
  replication_group_id = "${{var.project_name}}-cache"
  description          = "Redis cache for ${{var.project_name}}"

  engine               = "{engine}"
  engine_version       = "7.0"
  node_type            = var.cache_node_type
  num_cache_clusters   = var.environment == "prod" ? 2 : 1
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.cache.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  automatic_failover_enabled = var.environment == "prod"

  tags = var.tags
}}
"""

    def _aws_queue_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS SQS configuration."""
        return f"""# SQS Queue
resource "aws_sqs_queue" "main" {{
  name = "${{var.project_name}}-queue"

  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
  max_message_size           = 262144

  receive_wait_time_seconds = 20

  redrive_policy = jsonencode({{
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  }})

  tags = var.tags
}}

resource "aws_sqs_queue" "dlq" {{
  name = "${{var.project_name}}-dlq"

  message_retention_seconds = 1209600

  tags = var.tags
}}
"""

    def _aws_storage_config(
        self, config: InfrastructureConfig, project_name: str
    ) -> str:
        """Generate AWS S3 configuration."""
        return f"""# S3 Bucket
resource "aws_s3_bucket" "main" {{
  bucket = "${{var.project_name}}-${{var.environment}}-${{data.aws_caller_identity.current.account_id}}"

  tags = var.tags
}}

resource "aws_s3_bucket_versioning" "main" {{
  bucket = aws_s3_bucket.main.id

  versioning_configuration {{
    status = var.environment == "prod" ? "Enabled" : "Disabled"
  }}
}}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {{
  bucket = aws_s3_bucket.main.id

  rule {{
    apply_server_side_encryption_by_default {{
      sse_algorithm = "AES256"
    }}
  }}
}}

resource "aws_s3_bucket_public_access_block" "main" {{
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}}
"""

    def _aws_alb_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS ALB configuration."""
        return f"""# Application Load Balancer
resource "aws_security_group" "alb" {{
  count = var.enable_load_balancer ? 1 : 0

  name        = "${{var.project_name}}-alb-sg"
  description = "Security group for ALB"
  vpc_id      = module.vpc.vpc_id

  ingress {{
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  ingress {{
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  tags = var.tags
}}

resource "aws_lb" "app" {{
  count = var.enable_load_balancer ? 1 : 0

  name               = "${{var.project_name}}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  subnets            = module.vpc.public_subnets

  enable_deletion_protection = var.environment == "prod"

  tags = var.tags
}}

resource "aws_lb_target_group" "app" {{
  count = var.enable_load_balancer ? 1 : 0

  name        = "${{var.project_name}}-tg"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {{
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }}

  tags = var.tags
}}

resource "aws_lb_listener" "http" {{
  count = var.enable_load_balancer ? 1 : 0

  load_balancer_arn = aws_lb.app[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {{
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[0].arn
  }}
}}
"""

    def _aws_cdn_config(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate AWS CloudFront configuration."""
        return f"""# CloudFront Distribution
resource "aws_cloudfront_distribution" "main" {{
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = var.environment == "prod" ? "PriceClass_All" : "PriceClass_100"

  origin {{
    domain_name = aws_s3_bucket.main.bucket_regional_domain_name
    origin_id   = "S3-${{aws_s3_bucket.main.id}}"

    s3_origin_config {{
      origin_access_identity = aws_cloudfront_origin_access_identity.main.cloudfront_access_identity_path
    }}
  }}

  default_cache_behavior {{
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${{aws_s3_bucket.main.id}}"

    forwarded_values {{
      query_string = false
      cookies {{
        forward = "none"
      }}
    }}

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }}

  restrictions {{
    geo_restriction {{
      restriction_type = "none"
    }}
  }}

  viewer_certificate {{
    cloudfront_default_certificate = true
  }}

  tags = var.tags
}}

resource "aws_cloudfront_origin_access_identity" "main" {{
  comment = "${{var.project_name}} OAI"
}}
"""

    def _aws_variables_tf(
        self, config: InfrastructureConfig, project_name: str
    ) -> str:
        """Generate AWS variables.tf."""
        variables = f"""# Variables
variable "project_name" {{
  description = "Project name for resource naming"
  type        = string
  default     = "{project_name}"
}}

variable "environment" {{
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "{config.environment}"
}}

variable "region" {{
  description = "AWS region"
  type        = string
  default     = "{config.region}"
}}

variable "tags" {{
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {{}}
}}

variable "vpc_cidr" {{
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}}
"""

        if config.compute_type == "container":
            variables += f"""
variable "container_image" {{
  description = "Container image to deploy"
  type        = string
  default     = "{project_name}:latest"
}}

variable "container_port" {{
  description = "Container port"
  type        = number
  default     = {config.container_port}
}}

variable "container_cpu" {{
  description = "Container CPU units"
  type        = number
  default     = 256
}}

variable "container_memory" {{
  description = "Container memory (MB)"
  type        = number
  default     = 512
}}

variable "enable_load_balancer" {{
  description = "Enable load balancer"
  type        = bool
  default     = {str(config.needs_load_balancer).lower()}
}}
"""
        elif config.compute_type == "serverless":
            variables += """
variable "lambda_handler" {
  description = "Lambda handler"
  type        = string
  default     = "main.handler"
}

variable "lambda_zip_path" {
  description = "Path to Lambda deployment package"
  type        = string
  default     = "lambda.zip"
}

variable "lambda_timeout" {
  description = "Lambda timeout (seconds)"
  type        = number
  default     = 30
}

variable "lambda_memory" {
  description = "Lambda memory (MB)"
  type        = number
  default     = 256
}
"""
        elif config.compute_type == "kubernetes":
            variables += """
variable "eks_instance_type" {
  description = "EKS node instance type"
  type        = string
  default     = "t3.medium"
}
"""
        else:
            variables += f"""
variable "instance_type" {{
  description = "EC2 instance type"
  type        = string
  default     = "{config.instance_type}"
}}

variable "container_port" {{
  description = "Application port"
  type        = number
  default     = {config.container_port}
}}
"""

        if config.needs_database:
            variables += """
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage (GB)"
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "RDS max allocated storage (GB)"
  type        = number
  default     = 100
}

variable "db_username" {
  description = "Database username"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}
"""

        if config.needs_cache:
            variables += """
variable "cache_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}
"""

        return variables

    def _aws_outputs_tf(self, config: InfrastructureConfig) -> str:
        """Generate AWS outputs.tf."""
        outputs = """# Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnets" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnets
}
"""

        if config.compute_type == "container":
            outputs += """
output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.app.name
}
"""
            if config.needs_load_balancer:
                outputs += """
output "alb_dns_name" {
  description = "ALB DNS name"
  value       = var.enable_load_balancer ? aws_lb.app[0].dns_name : null
}
"""
        elif config.compute_type == "serverless":
            outputs += """
output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.app.function_name
}

output "api_gateway_url" {
  description = "API Gateway URL"
  value       = aws_apigatewayv2_api.app.api_endpoint
}
"""
        elif config.compute_type == "kubernetes":
            outputs += """
output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}
"""

        if config.needs_database:
            if config.database_type in ("postgres", "mysql"):
                outputs += """
output "database_endpoint" {
  description = "Database endpoint"
  value       = aws_db_instance.main.endpoint
}
"""
            elif config.database_type == "dynamodb":
                outputs += """
output "dynamodb_table_name" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.main.name
}
"""

        if config.needs_cache:
            outputs += """
output "cache_endpoint" {
  description = "ElastiCache endpoint"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}
"""

        if config.needs_storage:
            outputs += """
output "s3_bucket_name" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.main.id
}
"""

        return outputs

    def _aws_tfvars(self, config: InfrastructureConfig, project_name: str) -> str:
        """Generate terraform.tfvars."""
        tfvars = f"""# Terraform Variables
project_name = "{project_name}"
environment  = "{config.environment}"
region       = "{config.region}"

tags = {{
  Project     = "{project_name}"
  Environment = "{config.environment}"
  ManagedBy   = "Terraform"
}}
"""
        if config.needs_database:
            tfvars += """
# Database credentials (use environment variables or secrets manager in production)
# db_username = "admin"
# db_password = "CHANGE_ME"
"""
        return tfvars

    def _generate_gcp_terraform(
        self, config: InfrastructureConfig, project_name: str
    ) -> dict[str, str]:
        """Generate GCP Terraform configuration."""
        files = {}

        files["providers.tf"] = f"""# GCP Provider Configuration
terraform {{
  required_version = ">= 1.0"

  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
  }}
}}

provider "google" {{
  project = var.project_id
  region  = var.region
}}
"""

        files["variables.tf"] = f"""# Variables
variable "project_id" {{
  description = "GCP project ID"
  type        = string
}}

variable "project_name" {{
  description = "Project name for resource naming"
  type        = string
  default     = "{project_name}"
}}

variable "region" {{
  description = "GCP region"
  type        = string
  default     = "{config.region}"
}}

variable "environment" {{
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "{config.environment}"
}}
"""

        main_sections = ["# Main Configuration"]

        if config.compute_type == "container":
            main_sections.append(f"""# Cloud Run Service
resource "google_cloud_run_v2_service" "app" {{
  name     = "${{var.project_name}}-app"
  location = var.region

  template {{
    containers {{
      image = var.container_image

      ports {{
        container_port = {config.container_port}
      }}

      resources {{
        limits = {{
          cpu    = "1"
          memory = "512Mi"
        }}
      }}

      env {{
        name  = "ENVIRONMENT"
        value = var.environment
      }}
    }}

    scaling {{
      min_instance_count = var.environment == "prod" ? 1 : 0
      max_instance_count = var.environment == "prod" ? 10 : 3
    }}
  }}

  traffic {{
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }}
}}

resource "google_cloud_run_v2_service_iam_member" "public" {{
  count    = var.environment != "prod" ? 1 : 0
  project  = google_cloud_run_v2_service.app.project
  location = google_cloud_run_v2_service.app.location
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}}

variable "container_image" {{
  description = "Container image"
  type        = string
  default     = "gcr.io/${{var.project_id}}/{project_name}:latest"
}}
""")

        if config.needs_database and config.database_type == "postgres":
            main_sections.append("""# Cloud SQL
resource "google_sql_database_instance" "main" {
  name             = "${var.project_name}-db"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = var.environment == "prod" ? "db-custom-2-4096" : "db-f1-micro"

    backup_configuration {
      enabled = var.environment == "prod"
    }

    ip_configuration {
      ipv4_enabled    = true
      private_network = google_compute_network.main.id
    }
  }

  deletion_protection = var.environment == "prod"
}

resource "google_sql_database" "main" {
  name     = replace(var.project_name, "-", "_")
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "main" {
  name     = var.db_username
  instance = google_sql_database_instance.main.name
  password = var.db_password
}

variable "db_username" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}
""")

        if config.needs_cache:
            main_sections.append("""# Memorystore Redis
resource "google_redis_instance" "main" {
  name           = "${var.project_name}-cache"
  tier           = var.environment == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb = var.environment == "prod" ? 2 : 1
  region         = var.region

  authorized_network = google_compute_network.main.id
}
""")

        if config.needs_storage:
            main_sections.append("""# Cloud Storage
resource "google_storage_bucket" "main" {
  name     = "${var.project_name}-${var.environment}-${var.project_id}"
  location = var.region

  uniform_bucket_level_access = true

  versioning {
    enabled = var.environment == "prod"
  }
}
""")

        # VPC for private resources
        if config.needs_database or config.needs_cache:
            main_sections.append("""# VPC Network
resource "google_compute_network" "main" {
  name                    = "${var.project_name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "${var.project_name}-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.main.id
}
""")

        files["main.tf"] = "\n".join(main_sections)

        files["outputs.tf"] = """# Outputs
output "cloud_run_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.app.uri
}
"""

        files["terraform.tfvars"] = f"""# Terraform Variables
project_id   = "YOUR_PROJECT_ID"
project_name = "{project_name}"
environment  = "{config.environment}"
region       = "{config.region}"
"""

        return files

    def _generate_azure_terraform(
        self, config: InfrastructureConfig, project_name: str
    ) -> dict[str, str]:
        """Generate Azure Terraform configuration."""
        files = {}

        files["providers.tf"] = """# Azure Provider Configuration
terraform {
  required_version = ">= 1.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}
"""

        files["variables.tf"] = f"""# Variables
variable "project_name" {{
  description = "Project name for resource naming"
  type        = string
  default     = "{project_name}"
}}

variable "location" {{
  description = "Azure region"
  type        = string
  default     = "{config.region}"
}}

variable "environment" {{
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "{config.environment}"
}}
"""

        main_sections = ["""# Resource Group
resource "azurerm_resource_group" "main" {
  name     = "${var.project_name}-${var.environment}-rg"
  location = var.location

  tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
"""]

        if config.compute_type == "container":
            main_sections.append(f"""# Container App
resource "azurerm_container_app_environment" "main" {{
  name                = "${{var.project_name}}-env"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}}

resource "azurerm_container_app" "app" {{
  name                         = "${{var.project_name}}-app"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  template {{
    container {{
      name   = "app"
      image  = var.container_image
      cpu    = 0.25
      memory = "0.5Gi"
    }}

    min_replicas = var.environment == "prod" ? 1 : 0
    max_replicas = var.environment == "prod" ? 10 : 3
  }}

  ingress {{
    external_enabled = true
    target_port      = {config.container_port}
    traffic_weight {{
      percentage      = 100
      latest_revision = true
    }}
  }}
}}

variable "container_image" {{
  description = "Container image"
  type        = string
  default     = "{project_name}:latest"
}}
""")

        if config.needs_database and config.database_type == "postgres":
            main_sections.append("""# PostgreSQL Flexible Server
resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "${var.project_name}-db"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "15"
  administrator_login    = var.db_username
  administrator_password = var.db_password
  sku_name               = var.environment == "prod" ? "GP_Standard_D2s_v3" : "B_Standard_B1ms"
  storage_mb             = 32768

  tags = azurerm_resource_group.main.tags
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = replace(var.project_name, "-", "_")
  server_id = azurerm_postgresql_flexible_server.main.id
}

variable "db_username" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}
""")

        if config.needs_cache:
            main_sections.append("""# Azure Cache for Redis
resource "azurerm_redis_cache" "main" {
  name                = "${var.project_name}-cache"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  capacity            = 0
  family              = "C"
  sku_name            = var.environment == "prod" ? "Standard" : "Basic"

  tags = azurerm_resource_group.main.tags
}
""")

        if config.needs_storage:
            main_sections.append("""# Storage Account
resource "azurerm_storage_account" "main" {
  name                     = replace("${var.project_name}${var.environment}", "-", "")
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = var.environment == "prod" ? "GRS" : "LRS"

  tags = azurerm_resource_group.main.tags
}

resource "azurerm_storage_container" "main" {
  name                  = "data"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}
""")

        files["main.tf"] = "\n".join(main_sections)

        files["outputs.tf"] = """# Outputs
output "resource_group_name" {
  description = "Resource group name"
  value       = azurerm_resource_group.main.name
}

output "container_app_url" {
  description = "Container App URL"
  value       = "https://${azurerm_container_app.app.latest_revision_fqdn}"
}
"""

        files["terraform.tfvars"] = f"""# Terraform Variables
project_name = "{project_name}"
environment  = "{config.environment}"
location     = "{config.region}"
"""

        return files

    def _terraform_gitignore(self) -> str:
        """Generate .gitignore for Terraform."""
        return """# Terraform
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl
*.tfvars
!terraform.tfvars.example
crash.log
*.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
.terraformrc
terraform.rc
"""

    def _terraform_readme(
        self, config: InfrastructureConfig, project_name: str
    ) -> str:
        """Generate README for Terraform configuration."""
        return f"""# {project_name} Infrastructure

Terraform configuration for {project_name} on {config.cloud_provider.upper()}.

## Prerequisites

- Terraform >= 1.0
- {config.cloud_provider.upper()} CLI configured
- Appropriate permissions

## Usage

1. Initialize Terraform:
   ```bash
   terraform init
   ```

2. Review the plan:
   ```bash
   terraform plan
   ```

3. Apply the configuration:
   ```bash
   terraform apply
   ```

4. Destroy resources:
   ```bash
   terraform destroy
   ```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| project_name | Project name | {project_name} |
| environment | Environment | {config.environment} |
| region | Cloud region | {config.region} |

## Resources Created

- VPC/Network
- {'ECS/Cloud Run/Container App' if config.compute_type == 'container' else 'Compute resources'}
{f'- RDS/{config.database_type}' if config.needs_database else ''}
{f'- ElastiCache/Memorystore/Redis ({config.cache_type})' if config.needs_cache else ''}
{f'- S3/GCS/Blob Storage' if config.needs_storage else ''}

## Generated By

This configuration was generated by Sindri.
"""


class GeneratePulumiTool(Tool):
    """Generate Pulumi configuration files.

    Creates Pulumi Python or TypeScript code based on project detection.
    """

    name = "generate_pulumi"
    description = """Generate Pulumi infrastructure code.

Creates Pulumi Python or TypeScript code for cloud infrastructure.

Examples:
- generate_pulumi() - Auto-detect and generate Pulumi Python
- generate_pulumi(language="typescript") - Generate TypeScript
- generate_pulumi(provider="gcp") - Generate for Google Cloud
- generate_pulumi(dry_run=true) - Preview without creating files"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to project directory (default: current directory)",
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for Pulumi files (default: infra/)",
            },
            "language": {
                "type": "string",
                "description": "Pulumi language: 'python', 'typescript'",
                "enum": ["python", "typescript"],
            },
            "provider": {
                "type": "string",
                "description": "Cloud provider: 'aws', 'gcp', 'azure'",
                "enum": ["aws", "gcp", "azure"],
            },
            "project_name": {
                "type": "string",
                "description": "Project name",
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview without creating files",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        output_dir: Optional[str] = None,
        language: str = "python",
        provider: str = "aws",
        project_name: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Generate Pulumi configuration files."""
        project_path = self._resolve_path(path or ".")

        if not project_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Project path does not exist: {project_path}",
            )

        if not project_name:
            project_name = project_path.name.lower().replace("_", "-").replace(" ", "-")

        # Generate files
        if language == "python":
            files = self._generate_python_pulumi(provider, project_name)
        else:
            files = self._generate_typescript_pulumi(provider, project_name)

        output_path = project_path / (output_dir or "infra")

        if dry_run:
            output = "Pulumi configuration preview:\n\n"
            for filename, content in files.items():
                output += f"--- {filename} ---\n{content}\n\n"
            return ToolResult(
                success=True,
                output=output,
                metadata={
                    "dry_run": True,
                    "language": language,
                    "provider": provider,
                    "files": list(files.keys()),
                },
            )

        try:
            output_path.mkdir(parents=True, exist_ok=True)

            for filename, content in files.items():
                (output_path / filename).write_text(content)

            return ToolResult(
                success=True,
                output=f"Generated Pulumi {language} configuration in {output_path}\n\n"
                + "Files created:\n"
                + "\n".join(f"  - {f}" for f in files.keys())
                + "\n\nNext steps:\n"
                + "  1. cd infra/\n"
                + f"  2. {'pip install -r requirements.txt' if language == 'python' else 'npm install'}\n"
                + "  3. pulumi stack init dev\n"
                + "  4. pulumi up",
                metadata={
                    "language": language,
                    "provider": provider,
                    "output_dir": str(output_path),
                    "files": list(files.keys()),
                },
            )
        except Exception as e:
            return ToolResult(
                success=False, output="", error=f"Failed to write Pulumi files: {str(e)}"
            )

    def _generate_python_pulumi(
        self, provider: str, project_name: str
    ) -> dict[str, str]:
        """Generate Python Pulumi code."""
        files = {}

        files["Pulumi.yaml"] = f"""name: {project_name}
runtime: python
description: Infrastructure for {project_name}
"""

        files["Pulumi.dev.yaml"] = f"""config:
  {provider}:region: us-east-1
"""

        files["requirements.txt"] = f"""pulumi>=3.0.0
pulumi-{provider}>=6.0.0
"""

        if provider == "aws":
            files["__main__.py"] = f'''"""Pulumi infrastructure for {project_name}."""

import pulumi
import pulumi_aws as aws

# Configuration
config = pulumi.Config()
environment = config.get("environment") or "dev"
project_name = "{project_name}"

# VPC
vpc = aws.ec2.Vpc(
    f"{{project_name}}-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={{
        "Name": f"{{project_name}}-vpc",
        "Environment": environment,
    }},
)

# Internet Gateway
igw = aws.ec2.InternetGateway(
    f"{{project_name}}-igw",
    vpc_id=vpc.id,
    tags={{
        "Name": f"{{project_name}}-igw",
        "Environment": environment,
    }},
)

# Public Subnet
public_subnet = aws.ec2.Subnet(
    f"{{project_name}}-public-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    map_public_ip_on_launch=True,
    availability_zone="us-east-1a",
    tags={{
        "Name": f"{{project_name}}-public-subnet",
        "Environment": environment,
    }},
)

# Route Table
route_table = aws.ec2.RouteTable(
    f"{{project_name}}-rt",
    vpc_id=vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=igw.id,
        )
    ],
    tags={{
        "Name": f"{{project_name}}-rt",
        "Environment": environment,
    }},
)

# Route Table Association
aws.ec2.RouteTableAssociation(
    f"{{project_name}}-rta",
    subnet_id=public_subnet.id,
    route_table_id=route_table.id,
)

# Security Group
security_group = aws.ec2.SecurityGroup(
    f"{{project_name}}-sg",
    vpc_id=vpc.id,
    description="Security group for {{project_name}}",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=80,
            to_port=80,
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=443,
            to_port=443,
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1",
            from_port=0,
            to_port=0,
            cidr_blocks=["0.0.0.0/0"],
        )
    ],
    tags={{
        "Name": f"{{project_name}}-sg",
        "Environment": environment,
    }},
)

# Exports
pulumi.export("vpc_id", vpc.id)
pulumi.export("public_subnet_id", public_subnet.id)
pulumi.export("security_group_id", security_group.id)
'''
        elif provider == "gcp":
            files["__main__.py"] = f'''"""Pulumi infrastructure for {project_name}."""

import pulumi
import pulumi_gcp as gcp

# Configuration
config = pulumi.Config()
environment = config.get("environment") or "dev"
project_name = "{project_name}"

# Cloud Run Service
service = gcp.cloudrun.Service(
    f"{{project_name}}-service",
    location="us-central1",
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image="gcr.io/cloudrun/hello",
                )
            ],
        ),
    ),
    traffics=[
        gcp.cloudrun.ServiceTrafficArgs(
            percent=100,
            latest_revision=True,
        )
    ],
)

# IAM member to make the service public
gcp.cloudrun.IamMember(
    f"{{project_name}}-invoker",
    service=service.name,
    location=service.location,
    role="roles/run.invoker",
    member="allUsers",
)

# Exports
pulumi.export("service_url", service.statuses[0].url)
'''

        files[".gitignore"] = """# Pulumi
.pulumi/
*.pyc
__pycache__/
venv/
.venv/
"""

        return files

    def _generate_typescript_pulumi(
        self, provider: str, project_name: str
    ) -> dict[str, str]:
        """Generate TypeScript Pulumi code."""
        files = {}

        files["Pulumi.yaml"] = f"""name: {project_name}
runtime: nodejs
description: Infrastructure for {project_name}
"""

        files["Pulumi.dev.yaml"] = f"""config:
  {provider}:region: us-east-1
"""

        files["package.json"] = f"""{{
  "name": "{project_name}-infra",
  "main": "index.ts",
  "devDependencies": {{
    "@types/node": "^20"
  }},
  "dependencies": {{
    "@pulumi/pulumi": "^3.0.0",
    "@pulumi/{provider}": "^6.0.0"
  }}
}}
"""

        files["tsconfig.json"] = """{
  "compilerOptions": {
    "strict": true,
    "outDir": "bin",
    "target": "ES2020",
    "module": "commonjs",
    "moduleResolution": "node",
    "sourceMap": true,
    "experimentalDecorators": true,
    "pretty": true,
    "noFallthroughCasesInSwitch": true,
    "noImplicitReturns": true,
    "forceConsistentCasingInFileNames": true
  },
  "files": ["index.ts"]
}
"""

        if provider == "aws":
            files["index.ts"] = f'''import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";

// Configuration
const config = new pulumi.Config();
const environment = config.get("environment") || "dev";
const projectName = "{project_name}";

// VPC
const vpc = new aws.ec2.Vpc(`${{projectName}}-vpc`, {{
    cidrBlock: "10.0.0.0/16",
    enableDnsHostnames: true,
    enableDnsSupport: true,
    tags: {{
        Name: `${{projectName}}-vpc`,
        Environment: environment,
    }},
}});

// Internet Gateway
const igw = new aws.ec2.InternetGateway(`${{projectName}}-igw`, {{
    vpcId: vpc.id,
    tags: {{
        Name: `${{projectName}}-igw`,
        Environment: environment,
    }},
}});

// Public Subnet
const publicSubnet = new aws.ec2.Subnet(`${{projectName}}-public-subnet`, {{
    vpcId: vpc.id,
    cidrBlock: "10.0.1.0/24",
    mapPublicIpOnLaunch: true,
    availabilityZone: "us-east-1a",
    tags: {{
        Name: `${{projectName}}-public-subnet`,
        Environment: environment,
    }},
}});

// Security Group
const securityGroup = new aws.ec2.SecurityGroup(`${{projectName}}-sg`, {{
    vpcId: vpc.id,
    description: `Security group for ${{projectName}}`,
    ingress: [
        {{
            protocol: "tcp",
            fromPort: 80,
            toPort: 80,
            cidrBlocks: ["0.0.0.0/0"],
        }},
        {{
            protocol: "tcp",
            fromPort: 443,
            toPort: 443,
            cidrBlocks: ["0.0.0.0/0"],
        }},
    ],
    egress: [
        {{
            protocol: "-1",
            fromPort: 0,
            toPort: 0,
            cidrBlocks: ["0.0.0.0/0"],
        }},
    ],
    tags: {{
        Name: `${{projectName}}-sg`,
        Environment: environment,
    }},
}});

// Exports
export const vpcId = vpc.id;
export const publicSubnetId = publicSubnet.id;
export const securityGroupId = securityGroup.id;
'''

        files[".gitignore"] = """# Pulumi
.pulumi/
node_modules/
bin/
"""

        return files


class ValidateTerraformTool(Tool):
    """Validate Terraform configuration files.

    Checks Terraform files for syntax and best practices.
    """

    name = "validate_terraform"
    description = """Validate Terraform configuration for syntax and best practices.

Examples:
- validate_terraform() - Validate Terraform in current directory
- validate_terraform(path="terraform/") - Validate specific directory
- validate_terraform(check_formatting=true) - Also check formatting"""

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to Terraform directory (default: current directory)",
            },
            "check_formatting": {
                "type": "boolean",
                "description": "Check terraform fmt formatting",
            },
        },
        "required": [],
    }

    async def execute(
        self,
        path: Optional[str] = None,
        check_formatting: bool = False,
        **kwargs,
    ) -> ToolResult:
        """Validate Terraform configuration."""
        terraform_path = self._resolve_path(path or ".")

        if not terraform_path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Path does not exist: {terraform_path}",
            )

        # Find Terraform files
        tf_files = list(terraform_path.glob("*.tf"))
        if not tf_files:
            return ToolResult(
                success=False,
                output="",
                error=f"No Terraform files found in: {terraform_path}",
            )

        results = {"errors": [], "warnings": [], "suggestions": []}

        for tf_file in tf_files:
            file_results = self._validate_file(tf_file)
            results["errors"].extend(file_results["errors"])
            results["warnings"].extend(file_results["warnings"])
            results["suggestions"].extend(file_results["suggestions"])

        # Build output
        output_lines = [f"Validating Terraform in: {terraform_path}"]
        output_lines.append(f"Files checked: {len(tf_files)}")

        if results["errors"]:
            output_lines.append("\nErrors:")
            for err in results["errors"]:
                output_lines.append(f"  - {err}")

        if results["warnings"]:
            output_lines.append("\nWarnings:")
            for warn in results["warnings"]:
                output_lines.append(f"  - {warn}")

        if results["suggestions"]:
            output_lines.append("\nSuggestions:")
            for sug in results["suggestions"]:
                output_lines.append(f"  - {sug}")

        if not results["errors"] and not results["warnings"]:
            output_lines.append("\nNo issues found!")

        return ToolResult(
            success=len(results["errors"]) == 0,
            output="\n".join(output_lines),
            metadata={
                "files_checked": len(tf_files),
                "errors": len(results["errors"]),
                "warnings": len(results["warnings"]),
                "suggestions": len(results["suggestions"]),
            },
        )

    def _validate_file(self, tf_file: Path) -> dict:
        """Validate a single Terraform file."""
        results = {"errors": [], "warnings": [], "suggestions": []}

        content = tf_file.read_text()
        filename = tf_file.name

        # Basic syntax checks
        brace_count = content.count("{") - content.count("}")
        if brace_count != 0:
            results["errors"].append(f"{filename}: Unbalanced braces")

        # Check for common issues
        if "var." in content and "variables.tf" not in str(tf_file):
            # Check if variables are defined
            if 'variable "' not in content:
                results["warnings"].append(
                    f"{filename}: Uses variables but no variable blocks found"
                )

        # Check for hardcoded values that should be variables
        if '"us-east-1"' in content and "variables.tf" not in str(tf_file):
            results["suggestions"].append(
                f"{filename}: Consider using a variable for region"
            )

        # Check for missing descriptions
        if 'variable "' in content:
            import re

            var_blocks = re.findall(r'variable\s+"([^"]+)"\s*\{([^}]+)\}', content)
            for var_name, var_content in var_blocks:
                if "description" not in var_content:
                    results["suggestions"].append(
                        f"{filename}: Variable '{var_name}' missing description"
                    )

        # Check for sensitive variables without sensitive flag
        sensitive_patterns = ["password", "secret", "key", "token"]
        for pattern in sensitive_patterns:
            if f'variable "{pattern}' in content.lower():
                if "sensitive = true" not in content:
                    results["warnings"].append(
                        f"{filename}: Variable containing '{pattern}' should be marked sensitive"
                    )

        # Check for required_providers
        if "providers.tf" in str(tf_file) or "main.tf" in str(tf_file):
            if "terraform {" in content and "required_providers" not in content:
                results["suggestions"].append(
                    f"{filename}: Consider adding required_providers block"
                )

        return results
