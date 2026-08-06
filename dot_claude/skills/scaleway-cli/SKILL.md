---
name: scaleway-cli
description: Use when running or writing Scaleway CLI (scw) commands — managing Scaleway instances, k8s Kapsule clusters, rdb databases, object storage buckets, load balancers, IAM, secrets, or any Scaleway cloud resource from the terminal. Also for scw config/profiles/auth issues, scripting scw with jq/xargs, or scw arg syntax errors.
---

# Scaleway CLI (scw)

## Overview

scw v2 command pattern: `scw <namespace> <resource> <verb> [positional-id] [arg=value ...]`

**Args are `key=value`, NOT `--flags`.** Lists indexed: `tags.0=prod tags.1=web`. Nested: `pools.0.node-type=DEV1-M`. Maps: `labels.{key}=v`.

Before guessing any arg, run `scw <ns> <resource> <verb> --help` — help lists every arg, its default, and enum values.

## Critical Gotchas (verified, cause data loss or broken commands)

| Trap | Reality |
|------|---------|
| `instance server delete` | Default `with-volumes=all` — **DELETES ALL ATTACHED VOLUMES**. To keep them: `with-volumes=none` (enum: none\|local\|block\|root\|all, not true/false) |
| `scw object cp` / `scw object ls` | **Do not exist.** `scw object` only manages buckets + generates tool configs. Upload/download files via rclone/s3cmd/mc/aws-cli: `scw object config install type=rclone` then `rclone copy file.txt scaleway:bucket/` |
| Ubuntu image names | `ubuntu_noble` (24.04), `ubuntu_jammy` (22.04, current default). NOT `ubuntu_24_04`. List: `scw marketplace image list` |
| `rdb backup restore` | Cannot cross regions. Cross-region = export + download + manual psql/mysql restore |
| k8s `private-network-id`, `pod-cidr`, `service-cidr` | Immutable after cluster creation |
| Boolean-looking args | Many are enums (`with-volumes`, `ip=new\|none\|dynamic\|...`) — check `--help` before writing `=true` |

## Auth & Config

- Setup: `scw init` (interactive) or `scw login` (browser OAuth). Keys from console.scaleway.com/iam/api-keys.
- Config file: `~/.config/scw/config.yaml` (override `$SCW_CONFIG_PATH`). Shared with terraform/SDKs. **Env vars beat config file.**
- Env vars: `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`, `SCW_DEFAULT_ORGANIZATION_ID`, `SCW_DEFAULT_REGION`, `SCW_DEFAULT_ZONE`, `SCW_PROFILE`.
- Profiles: `scw -p <name> ...` per-command; `scw config profile activate <name>` to switch default; `scw config profile list`.
- `scw info` — shows every setting AND where it came from (env/config/default). First debug step for auth issues.
- Regions: fr-par, nl-ams, pl-waw, it-mil. Zones: `<region>-1/2/3`.

## Output & Scripting

- `-o json` (or `json=pretty`), `-o yaml`, `-o human=Col1,Col2`, `-o template="{{ .ID }}"` (Go template).
- `-w / --wait` blocks until resource reaches stable state (create/start/stop/delete on instance, k8s, rdb).
- `zone=all` / `region=all` fans list commands across all zones/regions.

```bash
# IDs one per line → xargs, parallel
scw instance server list zone=all -o template="{{.ID}} zone={{.Zone}}" | xargs -P8 -L1 scw instance server reboot
# jq pipeline
scw -o json instance server list tags.0=staging | jq -r '.[].id' | xargs -L1 scw instance server start -w
```

## Common Recipes

```bash
# Create server: Ubuntu 24.04, extra 50GB block volume, tags
scw instance server create zone=fr-par-1 name=web1 type=DEV1-S image=ubuntu_noble \
  additional-volumes.0=block:50GB tags.0=prod tags.1=web
# root-volume variants: local:10GB | sbs:100GB:15000 (iops) | local:<snapshot_id>; image=none to boot from snapshot

# Delete server, KEEP volumes and IP
scw instance server delete <id> zone=fr-par-1 with-volumes=none

# k8s: merge cluster kubeconfig into ~/.kube/config (or $KUBECONFIG)
scw k8s kubeconfig install <cluster-id> region=fr-par   # keep-current-context=true to not switch

# k8s cluster create (pools nested)
scw k8s cluster create name=prod pools.0.name=default pools.0.node-type=DEV1-M pools.0.size=3 \
  pools.0.autoscaling=true pools.0.min-size=1 pools.0.max-size=5
# delete with volumes/LBs/private-networks: with-additional-resources=true

# Object storage (buckets only!)
scw object bucket create name=my-unique-bucket region=fr-par enable-versioning=true
scw object config install type=rclone     # then rclone for actual file transfer

# rdb passwordless connect (uses ~/.pgpass / mysql login-paths)
scw rdb instance connect <id>

# Open resource in web console
scw instance server get <id> --web
```

- Dates: RFC3339 or relative `-7d`, `+1h30m` (units: s m h d w mo y). `scw help date`, `scw help output` for built-in topics.
- Aliases: `scw alias create isl command="instance server list"` (stored in `cli.yaml`, get completion).
- Interactive: `scw shell`. Autocomplete: `scw autocomplete install`.

## Red Flags — Stop and Check --help

- Writing `--anything` as a resource arg (only global flags use dashes: `-o -p -w -D --web`)
- Writing `with-volumes=true/false` — it's an enum
- Any `scw object` file-transfer command — doesn't exist
- Guessing an image slug with version numbers/dots — use marketplace names (`ubuntu_noble`)
- Repeating an arg for a list — use `arg.0= arg.1=` indexing
