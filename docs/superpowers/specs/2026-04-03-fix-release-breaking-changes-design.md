# Fix Release Breaking Changes Detection

## Problem

All `feat`, `fix`, `refactor`, and `perf` commits are incorrectly classified as breaking changes in GitHub releases. This happens because `cliff.toml` has duplicate `commit_parsers` rules where the first set marks every commit with `breaking = true`. Since git-cliff uses first-match semantics, the correct rules (without `breaking`) are never reached.

## Solution

Remove the duplicate `breaking = true` rules and rely on git-cliff's built-in conventional commit detection (`conventional_commits = true` + `protect_breaking_commits = true`). This automatically detects breaking changes from:

- `BREAKING CHANGE:` footer in commit body
- `!` after commit type (e.g., `feat!: ...`)

## Changes

All changes are in `cliff.toml`:

### 1. `commit_parsers` — remove duplicate breaking rules

Before:
```toml
commit_parsers = [
    { message = "^feat", group = "Breaking Changes", breaking = true },
    { message = "^fix", group = "Breaking Changes", breaking = true },
    { message = "^refactor", group = "Breaking Changes", breaking = true },
    { message = "^perf", group = "Breaking Changes", breaking = true },
    { message = "^feat", group = "Features" },
    { message = "^fix", group = "Bug Fixes" },
    ...
]
```

After:
```toml
commit_parsers = [
    { message = "^feat", group = "Features" },
    { message = "^fix", group = "Bug Fixes" },
    { message = "^refactor", group = "Refactoring" },
    { message = "^perf", group = "Performance" },
    { message = "^docs", skip = true },
    { message = "^chore", skip = true },
    { message = "^style", skip = true },
    { message = "^test", skip = true },
    { message = "^ci", skip = true },
]
```

### 2. Tera template `body` — filter by `commit.breaking` flag instead of group name

The template iterates over groups and within each group separates breaking commits (by `commit.breaking` flag) into a "Breaking Changes" header, while non-breaking commits render under their normal group header.

### 3. `[git]` section — no changes

`conventional_commits = true` and `protect_breaking_commits = true` already handle automatic breaking change detection.
