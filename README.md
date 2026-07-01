# dotfiles

Managed with [chezmoi](https://www.chezmoi.io). Tracks WM/desktop configs
(sway, waybar, mako, fuzzel, kanshi, gtklock, etc.) and Claude Code config
(`CLAUDE.md`, `settings.json`, `skills/`, `hooks/`).

## New machine setup

```bash
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply Cyberoiide
```

This clones the repo into `~/.local/share/chezmoi` and applies every tracked
file into `$HOME` in one step.

### After first apply

1. **Recreate secrets** — `~/.config/zsh/secrets.zsh` is intentionally not in
   this repo (see `.chezmoiignore`). Create it by hand:
   ```bash
   mkdir -p ~/.config/zsh && chmod 700 ~/.config/zsh
   cat > ~/.config/zsh/secrets.zsh <<'EOF'
   export GITHUB_PERSONAL_ACCESS_TOKEN="..."
   export HEKA_GITLAB_TOKEN="..."
   export STRATUMN_GITLAB_TOKEN="..."
   EOF
   chmod 600 ~/.config/zsh/secrets.zsh
   ```
   `.zshrc` already sources this file if present.

2. **System files outside `$HOME`** — chezmoi only manages `$HOME`, so these
   need manual reapplication:
   - Disable `pam_faillock` (prevents soft-locking yourself out after N wrong
     passwords at login/sudo/lock screen):
     ```bash
     sudo sed -i -E 's/^(auth.*pam_faillock\.so.*)$/# \1/' /etc/pam.d/system-auth
     ```
     Note: a `pambase` package update can restore the original file — recheck
     after major system upgrades.

3. **Enable the kanshi user service** (if not picked up automatically):
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now kanshi.service
   ```

## Daily commands

```bash
chezmoi add ~/.config/foo/bar.conf   # start tracking a file (copies live → source)
chezmoi diff                          # preview pending changes (safe, no writes)
chezmoi apply                         # write source → live files
chezmoi edit ~/.zshrc                 # edit the SOURCE file in $EDITOR
chezmoi cd                            # cd into the source repo (~/.local/share/chezmoi)
```

## Updating this repo

```bash
chezmoi cd
git add <files>
git commit -m "..."
git push
```

Full workflow, secret-scanning rules, and what NOT to track:
see the `chezmoi-dotfiles` Claude Code skill in `.claude/skills/chezmoi-dotfiles/SKILL.md`.
