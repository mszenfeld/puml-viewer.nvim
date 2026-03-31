# GitHub Release Pipeline — Design Spec

## Overview

GitHub Actions workflow that automatically creates a GitHub Release with a changelog generated from Conventional Commits when a version tag is pushed.

## Trigger

Workflow triggers on push of tags matching `v[0-9]+.[0-9]+.[0-9]+*` (semver with `v` prefix, optional pre-release suffix like `-rc.1`).

```yaml
on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+*'
```

## Changelog Generation

Tool: `git-cliff` via `orhun/git-cliff-action`.

Configuration in `cliff.toml` at repo root.

### Sections (in order)

1. **Breaking Changes** — commits with `BREAKING CHANGE` footer or `!` after type (e.g., `feat!:`)
2. **Features** — `feat` type commits
3. **Bug Fixes** — `fix` type commits
4. **Refactoring** — `refactor` type commits
5. **Performance** — `perf` type commits

### Excluded from changelog

- `docs`, `chore`, `style`, `test`, `ci` — not relevant to plugin users

### Entry format

- Scope in italics (if present) + description: `- *(export)* resolve relative paths`
- No scope: `- resolve relative paths`

### Range

Changelog covers only changes between the previous tag and the current tag (not full history).

## GitHub Release

Tool: `softprops/action-gh-release`.

- **Name**: tag name (e.g., `v1.0.0`)
- **Body**: generated changelog
- **Pre-release**: auto-detected if tag contains `-` (e.g., `v1.0.0-rc.1`)
- **Draft**: no, published immediately
- **Artifacts**: none

## Workflow Structure

File: `.github/workflows/release.yml`

Single job, three steps:

1. **Checkout** — `actions/checkout@v4` with `fetch-depth: 0` (full history needed for tag comparison)
2. **Generate changelog** — `orhun/git-cliff-action` using `cliff.toml`, output to variable
3. **Create release** — `softprops/action-gh-release` with changelog body, tag name, pre-release detection

Permissions: `contents: write`.

## Files to Create

1. `.github/workflows/release.yml` — workflow definition
2. `cliff.toml` — git-cliff configuration
