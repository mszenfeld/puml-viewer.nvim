# Fix Release Breaking Changes Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `cliff.toml` so only commits explicitly marked as breaking (via `!` or `BREAKING CHANGE:` footer) appear under "Breaking Changes" in release notes.

**Architecture:** Single-file change to `cliff.toml` — remove duplicate `commit_parsers` rules that force `breaking = true` on all commits, and update the Tera template to filter by `commit.breaking` flag instead of group name.

**Tech Stack:** git-cliff, TOML, Tera templates

---

### Task 1: Remove duplicate breaking change commit parsers

**Files:**
- Modify: `cliff.toml:36-50`

- [ ] **Step 1: Remove the four `breaking = true` rules from `commit_parsers`**

Replace the entire `commit_parsers` block (lines 36-50) with:

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

- [ ] **Step 2: Verify TOML is valid**

Run: `cat cliff.toml`
Expected: No syntax errors; the `commit_parsers` array has exactly 9 entries, none with `breaking = true`.

---

### Task 2: Update Tera template to use `commit.breaking` flag

**Files:**
- Modify: `cliff.toml:1-25`

- [ ] **Step 1: Replace the `body` template**

Replace the current `body` value (lines 3-22) with:

```toml
body = """
{%- for group, commits in commits | group_by(attribute="group") -%}
{%- set breaking = commits | filter(attribute="breaking", value=true) -%}
{%- if breaking | length > 0 %}

### ⚠️ Breaking Changes

{% for commit in breaking -%}
- {% if commit.scope %}*({{ commit.scope }})* {% endif %}{{ commit.message }}
{% endfor -%}
{%- endif -%}

### {{ group }}

{% for commit in commits | filter(attribute="breaking", value=false) -%}
- {% if commit.scope %}*({{ commit.scope }})* {% endif %}{{ commit.message }}
{% endfor -%}
{%- endfor -%}
"""
```

This template:
- Iterates over commit groups (Features, Bug Fixes, etc.)
- Within each group, filters commits with `breaking == true` into a "Breaking Changes" section rendered first
- Renders non-breaking commits under their normal group header

- [ ] **Step 2: Verify the full `cliff.toml` looks correct**

Run: `cat cliff.toml`
Expected: The file should have the new template in `body`, the cleaned `commit_parsers`, and unchanged `[git]` section.

---

### Task 3: Test changelog generation locally

- [ ] **Step 1: Install git-cliff if not present**

Run: `which git-cliff || brew install git-cliff`

- [ ] **Step 2: Generate changelog for the latest tag to verify normal commits are not breaking**

Run: `git-cliff --config cliff.toml --latest`
Expected: Output should show commits grouped under "Features", "Bug Fixes", etc. — **not** under "Breaking Changes". The "Breaking Changes" section should be absent (since recent commits have no `!` or `BREAKING CHANGE:` footer).

- [ ] **Step 3: Test with a simulated breaking change commit message**

Run: `git-cliff --config cliff.toml --latest --with-commit "feat!: test breaking change detection"`
Expected: Output should include a "Breaking Changes" section containing "test breaking change detection", plus normal commits in their respective groups.

- [ ] **Step 4: Test with BREAKING CHANGE footer**

Run: `git-cliff --config cliff.toml --latest --with-commit "feat: add new api$(printf '\n\n')BREAKING CHANGE: old api removed"`
Expected: Output should include a "Breaking Changes" section containing "add new api".

---

### Task 4: Commit the fix

- [ ] **Step 1: Commit the changes**

```bash
git add cliff.toml
git commit -m "fix(release): detect breaking changes from conventional commit conventions only

Remove duplicate commit_parsers rules that marked all feat/fix/refactor/perf
commits as breaking. Now only commits with ! after type or BREAKING CHANGE
footer are classified as breaking changes."
```
