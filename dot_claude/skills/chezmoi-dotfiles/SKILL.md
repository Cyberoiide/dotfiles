---
name: chezmoi-dotfiles
description: How to back up, manage, and push cbosle's dotfiles with chezmoi + GitHub. Use whenever the user wants to add/track a config file, back up dotfiles, sync or apply dotfiles, edit a tracked config, commit/push dotfile changes, set up chezmoi on a new machine, or asks about their dotfiles repo. Also trigger on mentions of chezmoi, ~/.config backups, "track this config", or the dotfiles GitHub repo — even if chezmoi isn't named explicitly.
---

# chezmoi dotfiles (cbosle)

chezmoi manages this machine's dotfiles as a git repo. The **source** lives in
`~/.local/share/chezmoi` (a real git repo); your **home** files (`~/.zshrc`,
`~/.config/...`) are the live copies. `chezmoi add` copies a live file *into* the
source; `chezmoi apply` copies the source *back out* to home.

## Setup facts (this machine)

- Source dir: `~/.local/share/chezmoi`
- Remote: `git@github.com:Cyberoiide/dotfiles.git` (branch `main`)
- SSH: `github.com` uses `~/.ssh/id_ed25519_github` (see `~/.ssh/config`)
- Source-file naming: `~/.zshrc` → `dot_zshrc`, `~/.config/sway` → `dot_config/sway`,
  private files get a `private_` prefix, executables `executable_`. chezmoi handles
  this automatically — don't rename by hand.

## The golden rule: secrets never enter the source

Before adding anything or committing, **scan for secrets**. GitHub push protection
will block a push containing a token, and a leaked secret in git history is
permanent even after deletion.

- Real secrets (tokens, keys, passwords) live in `~/.config/zsh/secrets.zsh`
  (untracked, chmod 600, listed in `.chezmoiignore`). `.zshrc` sources it and
  references the vars (`$HEKA_GITLAB_TOKEN`, etc.) — never inline literals.
- To add a new secret: put the literal in `~/.config/zsh/secrets.zsh`, reference
  the var in the tracked file, `chezmoi add` the tracked file.
- Always run this before committing:
  ```bash
  cd ~/.local/share/chezmoi
  grep -rlIE "glpat-|gho_[A-Za-z0-9]|ghp_[A-Za-z0-9]|AKIA[A-Z0-9]|-----BEGIN|xox[baprs]-" . --exclude-dir=.git 2>/dev/null || echo CLEAN
  ```

## Daily workflow

### Track a new / changed file
```bash
chezmoi add ~/.config/foo/bar.conf     # copy live file into source
chezmoi diff                            # preview what apply would change (safe)
```
`chezmoi add` on an already-tracked file re-imports the current live version — this
is how you capture edits made directly in `~`.

### Edit a tracked file
Prefer editing the live file then `chezmoi add`, OR edit the source then apply:
```bash
chezmoi edit ~/.zshrc     # opens the SOURCE file in $EDITOR
chezmoi apply             # writes changes back to ~/.zshrc
```

### What NOT to add
`~/.config` holds app state and caches, not just config. Do **not** add:
- App state/caches: browsers (`BraveSoftware`, `mozilla`, `microsoft-edge`),
  `Code - OSS`, `~/.config/Claude` (Claude **Desktop** app cache, 600M+),
  `spotify`, `chezmoi` itself
- Secret stores: `gh/`, `glab-cli/`, `netbird/`
- Binaries / runtime state: wallpaper PNGs, `go/telemetry`, log files

When adding a directory that pulls in junk, remove it from the source afterward
(`rm` inside `~/.local/share/chezmoi/dot_config/...`) and add a matching rule to
`.chezmoiignore` so `apply` never recreates it and future `add`s skip it.

### Claude Code config (`~/.claude`)
Tracked (real config): `CLAUDE.md`, `RTK.md`, `settings.json`, `skills/`, `hooks/`.
`~/.claude` is a mix of config and heavy runtime state — add only the config, the
same way you'd curate `~/.config`:
```bash
chezmoi add ~/.claude/CLAUDE.md ~/.claude/RTK.md ~/.claude/settings.json \
            ~/.claude/skills ~/.claude/hooks
```
Do **not** add (all ignored in `.chezmoiignore`):
- `.credentials.json` — auth secret, never commit
- `settings.local.json` — machine-specific by convention (the `.local` suffix)
- Caches / runtime state: `plugins/` (100M+, re-downloadable), `security/`,
  `projects/`, `sessions/`, `session-env/`, `jobs/`, `cache/`, `paste-cache/`,
  `file-history/`, `shell-snapshots/`, `backups/`, `telemetry/`, `daemon/`,
  `ide/`, `downloads/`, `plans/`

Note: `~/.claude` (Claude **Code**) ≠ `~/.config/Claude` (Claude **Desktop** cache).
Track the former's config; never the latter.
`settings.json` carries machine-specific values (AWS profile, `/home/cbosle` paths)
— fine for a personal backup, but adjust on a new machine.

## Commit and push

Work inside the source repo. Commit in **small logical groups** (one concern per
commit), not one giant commit. **Never mention Claude / AI in commit messages.**

```bash
cd ~/.local/share/chezmoi      # or: chezmoi cd
# ... after the secret scan above passes ...
git add dot_config/sway
git commit -m "Add sway WM config"
git add dot_config/waybar dot_config/mako
git commit -m "Add waybar and mako configs"
git push -u origin main
```

If `git push` is rejected by GitHub push protection, a secret is in a commit —
**do not click the allow-secret URL**. Remove the secret from the file, move it to
`secrets.zsh`, and rewrite the offending commit (`git commit --amend` if it's the
last/only commit, otherwise rebase). Re-scan, then push.

## New machine (restore)
```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply Cyberoiide
```
Then recreate `~/.config/zsh/secrets.zsh` by hand (it's not in the repo) with the
current rotated tokens.

Re-register Claude Code MCP servers (`~/.claude.json` is runtime state, not tracked):
```bash
claude mcp add affine -- affine-mcp
claude mcp add --transport http outline https://wiki.sia.partners/mcp
```

### System files chezmoi can't track (`/etc`, out of `$HOME`)
chezmoi only manages paths under `$HOME` — `chezmoi target-path /etc/...` errors
with "not in ~/.local/share/chezmoi". Anything outside home needs manual redo on a
new machine. Current one:

- **pam_faillock disabled** in `/etc/pam.d/system-auth` (all 3 `pam_faillock.so`
  lines commented out) — prevents soft-locking yourself out after N wrong
  passwords at gtklock/login/sudo. Re-apply on a new machine:
  ```bash
  sudo sed -i -E 's/^(auth.*pam_faillock\.so.*)$/# \1/' /etc/pam.d/system-auth
  ```
  Note: a `pambase` package update can silently restore the original file —
  re-check this after major system upgrades.

## Verify before pushing (checklist)
1. Secret scan prints `CLEAN`.
2. `git status` shows only intended files; no app-state dirs or binaries.
3. `git log --oneline` messages are descriptive and Claude-free.
4. `du -sh --exclude=.git ~/.local/share/chezmoi` is small (KB, not MB) unless
   binaries were intentionally included.
