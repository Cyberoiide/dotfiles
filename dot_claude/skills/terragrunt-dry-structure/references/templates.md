# File templates

Copy-paste starting points. Replace `myplatform`, ports, names. Sections:

1. [environments/root.hcl — GitLab HTTP backend](#1-environmentsroothcl--gitlab-http-backend)
2. [environments/root.hcl — S3 backend variant](#2-remote_state-s3-variant)
3. [environments/&lt;env&gt;/terragrunt.hcl](#3-environmentsenvterragrunthcl)
4. [terraform/versions.tf](#4-terraformversionstf)
5. [terraform/variables.tf skeleton](#5-terraformvariablestf-skeleton)
6. [terraform/main.tf composition skeleton](#6-terraformmaintf-composition-skeleton)
7. [modules/settings/](#7-modulessettings)
8. [Domain module skeleton](#8-domain-module-skeleton)

## 1. environments/root.hcl — GitLab HTTP backend

```hcl
locals {
  environment      = replace(basename(get_original_terragrunt_dir()), "_", "-")
  layer_state_slug = "env-${local.environment}"

  # CI provides these; run_cmd fallbacks make local runs work with glab auth
  project_id     = get_env("CI_PROJECT_ID", run_cmd("--terragrunt-quiet", "sh", "-c", "glab api projects/:id | jq -r '.id'"))
  gitlab_api_uri = get_env("CI_API_V4_URL", "${chomp(run_cmd("--terragrunt-quiet", "sh", "-c", "glab config get gitlab_uri"))}/api/v4")

  # GLOBAL CONSTANTS — same in every environment
  base_cluster_name  = "myplatform"
  base_postgres_port = 5432
  base_redis_port    = 6379

  # FEATURE FLAGS — flipped here once proven in one env
  ff_enable_tight_security_groups = "true"
}

remote_state {
  backend = "http"
  config = {
    address        = "${local.gitlab_api_uri}/projects/${local.project_id}/terraform/state/${local.layer_state_slug}"
    lock_address   = "${local.gitlab_api_uri}/projects/${local.project_id}/terraform/state/${local.layer_state_slug}/lock"
    unlock_address = "${local.gitlab_api_uri}/projects/${local.project_id}/terraform/state/${local.layer_state_slug}/lock"
    username       = get_env("GITLAB_USERNAME")
    password       = get_env("GITLAB_TOKEN")
    lock_method    = "POST"
    unlock_method  = "DELETE"
    retry_wait_min = "5"
  }
}

# Every local that modules need must be re-exported as an input
inputs = {
  base_cluster_name               = local.base_cluster_name
  base_postgres_port              = local.base_postgres_port
  base_redis_port                 = local.base_redis_port
  ff_enable_tight_security_groups = local.ff_enable_tight_security_groups
}
```

## 2. remote_state S3 variant

Swap the `remote_state` block (and use `backend "s3" {}` in versions.tf):

```hcl
remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket         = "myplatform-tfstate-${get_aws_account_id()}"
    key            = "${local.layer_state_slug}/terraform.tfstate"
    region         = "eu-west-1"
    encrypt        = true
    dynamodb_table = "myplatform-tflock"
  }
}
```

## 3. environments/&lt;env&gt;/terragrunt.hcl

Directory name = environment name = state slug. Keep under ~50 lines.

```hcl
inputs = {
  aws_region              = "eu-west-1"
  aws_region_fallback     = "eu-west-3"
  aws_availability_zone_1 = "eu-west-1a"
  aws_availability_zone_2 = "eu-west-1b"

  network_config = {
    cidr_block : "10.20.0.0/16"          # unique block per environment
    aws_public_subnet_ip_1 : "10.20.0.0/24"
    aws_public_subnet_ip_2 : "10.20.1.0/24"
    aws_private_subnet_ip_1 : "10.20.2.0/24"
    aws_private_subnet_ip_2 : "10.20.3.0/24"
  }

  node_pool_sizes = {
    default : 15
    workload : 5
  }

  # Temporary pins go here, with their exit condition:
  # nodes still on 1.29; drop once walked up to 1.31
  # ff_eks_k8s_nodes_version = "1.29"
}

terraform {
  source = "../../terraform//"
}

include "root" {   # label required by modern terragrunt
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
```

## 4. terraform/versions.tf

Backend stub is empty — terragrunt injects the config. All providers and aliases live here, nowhere else.

```hcl
terraform {
  required_version = "~> 1.3"
  backend "http" {}   # or backend "s3" {} — must match root.hcl remote_state

  required_providers {
    aws    = { version = "~> 5.0", source = "hashicorp/aws" }
    random = { version = "~> 3.0", source = "hashicorp/random" }
  }
}

provider "aws" {
  region = var.aws_region
}

# us-east-1 pin: CloudFront certs and Lambda@Edge only exist there
provider "aws" {
  alias  = "cloudfront"
  region = "us-east-1"
}

provider "aws" {
  alias  = "fallback"
  region = var.aws_region_fallback
}

# Cross-account access via assume_role; role ARN discovered by settings module
provider "aws" {
  alias  = "shared_services"
  region = "eu-west-1"
  assume_role {
    role_arn = module.settings.shared_services_assume_role_arn
  }
}
```

## 5. terraform/variables.tf skeleton

Naming: `base_*` platform constants, `ff_*` flags (safe default!), `config_*` fixed thresholds, per-env values bare.

```hcl
variable "aws_region" { type = string }
variable "aws_region_fallback" { type = string }
variable "aws_availability_zone_1" { type = string }
variable "aws_availability_zone_2" { type = string }

variable "base_cluster_name" { type = string }
variable "base_postgres_port" { type = string }

variable "ff_enable_tight_security_groups" {
  type    = bool
  default = false          # flags default OFF; root.hcl turns them on
}

variable "network_config" {
  description = "VPC network configuration"
  type = object({
    cidr_block              = string
    aws_public_subnet_ip_1  = string
    aws_public_subnet_ip_2  = string
    aws_private_subnet_ip_1 = string
    aws_private_subnet_ip_2 = string
  })
}

variable "node_pool_sizes" {
  type = object({
    default  = number
    workload = number
  })
}
```

## 6. terraform/main.tf composition skeleton

Only `module` and `locals` blocks. No resources. Dependencies = output-to-input wiring.

```hcl
module "settings" {
  source     = "./modules/settings"
  aws_region = var.aws_region
  providers = {
    aws.shared_services = aws.shared_services
  }
}

locals {
  base_stage                     = module.settings.base_stage
  base_aws_account_id            = module.settings.base_aws_account_id
  base_is_production_environment = contains(["release", "release-us"], local.base_stage)

  # Globally-unique names embed account + region so envs can never collide
  alb_logs_bucket_name = "alb-logs-${local.base_aws_account_id}-${var.aws_region}"
}

module "networking" {
  source = "./modules/networking"
  providers = {
    aws.shared_services = aws.shared_services
  }

  aws_region     = var.aws_region
  network_config = var.network_config
  base_stage     = local.base_stage
}

module "database" {
  source = "./modules/database"

  base_postgres_port             = var.base_postgres_port
  base_is_production_environment = local.base_is_production_environment

  # cross-module wiring — the dependency graph, written explicitly
  base_vpc_id                = module.networking.base_vpc_id
  subnet_base_private_one_id = module.networking.subnet_base_private_one_id
  sg_base_postgres_id        = module.networking.sg_base_postgres_id
}

# Optional subsystem: whole module behind a flag
module "reporting" {
  count  = var.reporting_enabled ? 1 : 0
  source = "./modules/reporting"

  aws_region = var.aws_region
}
```

## 7. modules/settings/

`main.tf` — pure discovery, data sources only (plus the odd shared SSM write):

```hcl
data "aws_caller_identity" "base" {}
data "aws_organizations_organization" "base" {}

# Environment identity written into the account at bootstrap time
data "aws_ssm_parameter" "base_opsconf_environment" {
  name = "/opsconf/environment"
}

data "aws_ssm_parameter" "base_opsconf_dns_namespace" {
  name = "/opsconf/dns_namespace"
}

# Latest-AMI lookup via public SSM path — never a hardcoded, aging AMI ID
data "aws_ssm_parameter" "base_bastion_host_ami_id" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_kms_key" "base_rds" {
  key_id = "alias/myplatform/rds"
}

data "aws_route53_zone" "environment_zone" {
  name         = data.aws_ssm_parameter.base_opsconf_dns_namespace.value
  private_zone = false
}

data "aws_ssm_parameter" "shared_services_assume_role_arn" {
  name = "base_shared_services_vpc_assume_role_arn"
}
```

`outputs.tf`:

```hcl
output "base_aws_account_id" {
  value = data.aws_caller_identity.base.account_id
}

output "base_stage" {
  value     = data.aws_ssm_parameter.base_opsconf_environment.value
  sensitive = true
}

output "base_dns_namespace" {
  value     = data.aws_ssm_parameter.base_opsconf_dns_namespace.value
  sensitive = true
}

output "route53_environment_zone_id" {
  value = data.aws_route53_zone.environment_zone.zone_id
}

output "kms_key_base_rds_arn" {
  value = data.aws_kms_key.base_rds.arn
}

output "shared_services_assume_role_arn" {
  value = data.aws_ssm_parameter.shared_services_assume_role_arn.value
}
```

`versions.tf`:

```hcl
terraform {
  required_providers {
    aws = {
      version               = "~> 5.0"
      source                = "hashicorp/aws"
      configuration_aliases = [aws.shared_services]
    }
  }
}
```

Bootstrap note: the `/opsconf/*` SSM parameters are written once per account (manually or by an account-bootstrap stack). They are the only per-account setup; everything else derives from them.

## 8. Domain module skeleton

Every module: `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`. Modules never define providers — only alias requirements.

`modules/database/versions.tf` (only when the module uses an alias):

```hcl
terraform {
  required_providers {
    aws = {
      version               = "~> 5.0"
      source                = "hashicorp/aws"
      configuration_aliases = [aws.fallback]
    }
  }
}
```

`modules/database/variables.tf` — declare exactly what the module consumes, nothing more:

```hcl
variable "base_postgres_port" { type = string }
variable "base_is_production_environment" { type = bool }
variable "base_vpc_id" { type = string }
variable "subnet_base_private_one_id" { type = string }
variable "sg_base_postgres_id" { type = string }
```

`modules/database/outputs.tf` — export what siblings need, keep the surface small:

```hcl
output "database_host" {
  value = aws_db_instance.base.address
}
```
