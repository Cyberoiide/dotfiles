---
name: terragrunt-dry-structure
description: Scaffold or refactor Terraform/Terragrunt repos into a DRY multi-environment structure - one shared root module, thin per-environment terragrunt.hcl files, a root.hcl that derives environment identity from the directory name, and a settings module that reads runtime identity from the cloud account. Use this whenever the user wants to create Terraform infrastructure with multiple environments (dev/staging/prod), set up Terragrunt, restructure copy-pasted per-env Terraform, add a new environment to an existing Terragrunt tree, or asks how to keep Terraform DRY, even if they don't say "Terragrunt" explicitly.
---

# Terragrunt DRY Structure

Reproduce a battle-tested multi-environment Terraform layout: **one codebase, N states**. Environments differ only by inputs, never by code. Extracted from a production platform running 6 environments (staging, demo, preprod, preprod_us, release, release_us) off a single root module.

## The layout

```
infrastructure/
├── environments/               # Terragrunt live tree (config only, no .tf files)
│   ├── root.hcl                # shared: backend, global inputs, env-name derivation
│   ├── staging/terragrunt.hcl  # ~40 lines: region, CIDRs, sizes, per-env pins
│   ├── demo/terragrunt.hcl
│   └── release/terragrunt.hcl
└── terraform/                  # ONE root module shared by every environment
    ├── main.tf                 # composition root: only module blocks, zero resources
    ├── variables.tf            # every input, typed; safe defaults for flags
    ├── versions.tf             # backend "http" {} stub + ALL provider blocks
    ├── outputs.tf
    └── modules/
        ├── settings/           # reads env identity from the cloud account
        ├── networking/
        ├── database/
        └── <domain>/           # one module per domain, not per resource type
```

Full copy-paste templates for every file: `references/templates.md`. Read it when scaffolding.

## The six principles

### 1. Environment = directory name, nothing else

`root.hcl` derives the environment from where Terragrunt was invoked:

```hcl
locals {
  environment      = replace(basename(get_original_terragrunt_dir()), "_", "-")
  layer_state_slug = "env-${local.environment}"
}
```

Adding an environment = `mkdir environments/qa` + one small `terragrunt.hcl`. No backend edits, no state-key strings to keep in sync — the directory name IS the state key. Underscores map to hyphens so directory names stay shell-friendly while slugs stay DNS-friendly.

### 2. Every environment points at the same code

Each env `terragrunt.hcl` contains only three things — inputs, source, include:

```hcl
inputs = {
  aws_region      = "eu-west-1"
  network_config  = { cidr_block : "10.20.0.0/16", ... }
  node_pool_sizes = { default : 15, workload : 5 }
}

terraform {
  source = "../../terraform//"   # trailing // marks the module root for terragrunt
}

include "root" {   # modern terragrunt requires the label
  path   = find_in_parent_folders("root.hcl")
  expose = true
}
```

If an env file grows a `generate` block, a hook, or more than ~50 lines of inputs, code is leaking into config — push it into the root module behind a variable instead.

### 3. Three tiers of inputs — put each value at the right altitude

| Tier | Lives in | Examples |
|------|----------|----------|
| Global constants & flags | `root.hcl` `inputs` | ports, base names, `ff_*` flags, org account IDs |
| Per-environment values | env `terragrunt.hcl` | region, AZs, CIDRs, pool sizes, SSO role IDs, temporary pins |
| Runtime/account identity | `settings` module (data sources) | account ID, stage name, DNS zone, KMS keys, AMI IDs |

The test: if you'd have to copy a value into every env file, it belongs in `root.hcl`. If Terraform can look it up from the account it's running in, it belongs in `settings` and shouldn't be an input at all.

### 4. The settings module: identity from the account, not from tfvars

The root module opens by asking the account "who am I?" via data sources — `aws_caller_identity`, `aws_organizations_organization`, SSM parameters like `/opsconf/environment` and `/opsconf/dns_namespace`, KMS alias lookups, latest-AMI SSM paths. Outputs feed everything else:

```hcl
module "settings" { source = "./modules/settings" ... }

locals {
  base_stage        = module.settings.base_stratumn_stage
  base_is_production = contains(["release", "release-us"], local.base_stage)
  alb_logs_bucket   = "alb-logs-${module.settings.base_aws_account_id}-${var.aws_region}"
}
```

Why: the same code deployed into a different AWS account picks up that account's identity automatically — no per-env tfvars for things the account already knows. Globally-unique names (S3 buckets) embed `${account_id}-${region}` so no environment can collide with another.

### 5. Composition root: main.tf wires, modules do

Root `main.tf` contains **only** `module` blocks and a `locals` block — zero `resource` blocks. Each domain module (networking, database, cluster, ingest...) receives:

- plain `var.*` passthroughs for config,
- `local.*` for settings-derived values,
- `module.<other>.<output>` for cross-module dependencies — this is the dependency graph, written explicitly:

```hcl
module "database" {
  source                     = "./modules/database"
  subnet_base_private_one_id = module.networking.subnet_base_private_one_id
  sg_base_postgres_id        = module.networking.sg_base_postgres_id
  base_is_production_environment = local.base_is_production_environment
}
```

No module reads another module's state; everything flows through outputs at the root. Optional subsystems are modules gated by a flag: `count = var.sqs_to_dynamodb_enabled ? 1 : 0`.

Split modules by **domain** (what a team changes together), not by resource type. A `database` module owning its instance, subnet group, and parameter group beats an `rds-instances` module plus a `parameter-groups` module.

### 6. Providers once, aliases down

All provider blocks live in the root `versions.tf`. Multi-region/multi-account needs are aliases, not per-module providers:

```hcl
provider "aws" { region = var.aws_region }                       # default
provider "aws" { alias = "cloudfront", region = "us-east-1" }    # Lambda@Edge/ACM must be us-east-1
provider "aws" { alias = "fallback",   region = var.aws_region_fallback }
provider "aws" {
  alias  = "shared_services"
  assume_role { role_arn = module.settings.shared_services_role_arn }  # cross-account
}
```

Root passes aliases explicitly (`providers = { aws.cloudfront = aws.cloudfront }`); child modules declare them in their own `versions.tf` via `configuration_aliases`. Every module gets its own small `versions.tf` pinning `~>` versions — no module silently floats.

## Conventions that keep it navigable

- **Prefix vocabulary**: `base_*` platform-wide values, `ff_*` feature flags, `config_*` fixed constants, `ssorole_*` SSO role IDs. A reader can tell a variable's tier and mutability from its name.
- **Feature flags** get safe defaults in `variables.tf` (`default = false`), get flipped globally in `root.hcl`, and can be overridden per env. Rollout = flip in one env file, then move the `true` up to `root.hcl`, then (later) delete the flag.
- **Migration phases** for multi-step rollouts: one `migration_phase` input compared against named thresholds (`config_migration_phase_certificates_ready = 4`), so `count = var.migration_phase >= var.config_migration_phase_certificates_ready ? 1 : 0` reads as prose.
- **Backend is injected, never written**: `versions.tf` has an empty `backend "http" {}` (or `backend "s3" {}`); `root.hcl`'s `remote_state` block fills it in. Credentials come from `get_env(...)`, with `run_cmd(...)` fallbacks so local runs work without exporting CI variables.
- **Temporary per-env pins carry their exit condition** as a comment ("drop this line once nodes reach 1.31"). A pin without an expiry becomes permanent drift.

## Workflow: scaffolding a new repo

1. Ask (or infer) the domains: what subsystems exist? (network, database, cluster, app services...). Each becomes one module under `terraform/modules/`.
2. Ask which backend: GitLab HTTP (templates default) or S3+DynamoDB — `references/templates.md` has both.
3. Create the tree and files from `references/templates.md`: `root.hcl`, one env dir, root `main.tf`/`variables.tf`/`versions.tf`, `settings` module, one domain module as the pattern to copy.
4. Sort every known value into its tier (principle 3) before writing variables — this decides most of the structure.
5. Verify: `cd environments/<env> && terragrunt init && terragrunt validate` (or `terragrunt plan` if credentials exist).

## Workflow: adding an environment to an existing tree

1. Copy the closest existing env's `terragrunt.hcl` into a new directory named after the environment.
2. Change only the per-env tier values (region, AZs, CIDRs — pick a non-overlapping block, sizes, SSO IDs).
3. Nothing else — no root.hcl edits, no backend config. `terragrunt plan` from the new directory.

## Workflow: refactoring copy-pasted per-env Terraform

1. Diff two environment copies. Values that differ → per-env inputs; identical values → `root.hcl` inputs; values derivable from the account → `settings` module data sources.
2. Promote one copy to `terraform/` as the shared root module, parameterize the diffs.
3. Create env `terragrunt.hcl` files, migrate state per env (`terragrunt init -migrate-state` or `terraform state pull/push`).
4. Prove zero-diff: `terragrunt plan` in each env must show no changes before touching anything else. Do one env at a time.
