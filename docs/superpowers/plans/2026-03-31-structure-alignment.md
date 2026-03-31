# Structure Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align repository structure with Neovim plugin conventions — `plugin/`, `ftdetect/`, `doc/` directories, optional `setup()`, lazy dependency validation.

**Architecture:** Move command/autocmd registration from `setup()` to `plugin/puml-viewer.lua` (auto-loaded by Neovim). Filetype detection to `ftdetect/`. `setup()` becomes a config-only override. Add vimdoc for `:help`.

**Tech Stack:** Lua (Neovim API), vimdoc format

---

### Task 1: Create `ftdetect/plantuml.lua`

Smallest, independent change. Registers additional PlantUML file extensions that Neovim does not detect natively.

**Files:**
- Create: `ftdetect/plantuml.lua`

- [ ] **Step 1: Create the ftdetect file**

```lua
vim.filetype.add({
  extension = {
    pu = "plantuml",
    uml = "plantuml",
    iuml = "plantuml",
  },
})
```

Only `.pu`, `.uml`, `.iuml`. Neovim already handles `.puml` and `.plantuml` natively.

- [ ] **Step 2: Verify**

Open Neovim and run:
```vim
:edit /tmp/test.iuml
:echo &filetype
```
Expected: `plantuml`

- [ ] **Step 3: Commit**

```bash
git add ftdetect/plantuml.lua
git commit -m "feat: add ftdetect for .pu/.uml/.iuml extensions"
```

---

### Task 2: Refactor `lua/puml-viewer/init.lua` — expose command handlers, lazy config

This is the core refactoring. Changes `init.lua` so that:
- `M.config` is initialized with defaults at module load time (no `setup()` needed)
- `setup()` only merges user options into `M.config`
- Command handlers are exposed as `M.cmd_preview`, `M.cmd_export`, `M.cmd_stop`
- `validate_dependencies()` is called lazily inside `cmd_preview` and `cmd_export`, not in `setup()`
- `register_commands()`, `register_autocmds()`, and `vim.filetype.add()` are removed (they move to `plugin/` and `ftdetect/`)

**Files:**
- Modify: `lua/puml-viewer/init.lua`

- [ ] **Step 1: Replace the full `init.lua` with refactored version**

```lua
local config = require("puml-viewer.config")
local server = require("puml-viewer.server")
local export = require("puml-viewer.export")
local utils = require("puml-viewer.utils")

local M = {}

-- Config is available immediately with defaults.
-- setup() overrides it with user options.
M.config = config.merge()

--- Validate that required dependencies are available.
---@return boolean
local function validate_dependencies()
  local errors = {}

  if vim.fn.executable("python3") == 0 then
    table.insert(errors, "python3 not found in PATH")
  end

  -- Split command to check just the executable name
  local cmd_parts = vim.split(M.config.plantuml_cmd, " ")
  if vim.fn.executable(cmd_parts[1]) == 0 then
    table.insert(errors, M.config.plantuml_cmd .. " not found in PATH")
  end

  if #errors > 0 then
    for _, err in ipairs(errors) do
      vim.notify("puml-viewer: " .. err, vim.log.levels.ERROR)
    end
    return false
  end

  return true
end

--- Detect browser open command for the current platform.
---@return string|nil
local function detect_browser_cmd()
  if vim.fn.executable("open") == 1 then
    return "open" -- macOS
  elseif vim.fn.executable("xdg-open") == 1 then
    return "xdg-open" -- Linux
  end
  return nil
end

--- Send update and open browser once the server is ready.
---@param port number The port the server is listening on
local function open_preview(port)
  -- Send current buffer content
  local content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")
  server.send_update(content)

  -- Open browser (include session token for authentication)
  local token = server.get_token()
  local url = "http://localhost:" .. port .. "?token=" .. (token or "")
  local browser_cmd = M.config.browser_cmd or detect_browser_cmd()

  if not browser_cmd then
    vim.notify("puml-viewer: no browser command found. Set browser_cmd in config.\nServer running at: " .. url, vim.log.levels.WARN)
    return
  end

  vim.fn.jobstart({ browser_cmd, url }, {
    on_exit = function(_, exit_code)
      if exit_code ~= 0 then
        vim.schedule(function()
          vim.notify("puml-viewer: failed to open browser. Server at: " .. url, vim.log.levels.WARN)
        end)
      end
    end,
  })
end

--- Start preview server and open browser.
function M.cmd_preview()
  if not utils.is_plantuml_file() then
    vim.notify("puml-viewer: not a PlantUML file", vim.log.levels.WARN)
    return
  end

  if not validate_dependencies() then
    return
  end

  local port = server.get_port()

  if port then
    open_preview(port)
    return
  end

  server.start(M.config, function(ready_port)
    open_preview(ready_port)
  end)
end

--- Export diagram to file.
---@param args table Command arguments from nvim_create_user_command
function M.cmd_export(args)
  if not validate_dependencies() then
    return
  end

  local format = M.config.export_format
  if args.args ~= "" then
    format = args.args
    if format ~= "png" and format ~= "svg" then
      vim.notify("puml-viewer: invalid format '" .. format .. "'. Use 'png' or 'svg'", vim.log.levels.ERROR)
      return
    end
  end
  export.export(format, M.config)
end

--- Stop the preview server.
function M.cmd_stop()
  if server.is_running() then
    server.stop()
    vim.notify("puml-viewer: server stopped", vim.log.levels.INFO)
  end
end

--- Setup the plugin with user options.
--- Optional — the plugin works with defaults if never called.
---@param user_opts table|nil User configuration options
function M.setup(user_opts)
  M.config = config.merge(user_opts)
end

return M
```

Key changes from the original:
- `current_config` local replaced with `M.config` (public, initialized at load)
- `cmd_preview`, `cmd_export`, `cmd_stop` promoted from local to `M.` (public)
- `validate_dependencies()` called inside `cmd_preview()` and `cmd_export()`, not in `setup()`
- `register_commands()` removed (moves to `plugin/`)
- `register_autocmds()` removed (moves to `plugin/`)
- `vim.filetype.add()` removed (moved to `ftdetect/`)
- `setup()` reduced to one line: merge config

- [ ] **Step 2: Run existing Python server tests to ensure no regressions**

```bash
python3 -m pytest tests/ -v
```

Expected: all tests pass (server code is unchanged).

- [ ] **Step 3: Commit**

```bash
git add lua/puml-viewer/init.lua
git commit -m "refactor: make setup() optional, expose command handlers"
```

---

### Task 3: Create `plugin/puml-viewer.lua`

Auto-loaded entry point that registers commands and autocommands. Depends on Task 2 (exposed command handlers).

**Files:**
- Create: `plugin/puml-viewer.lua`

- [ ] **Step 1: Create the plugin entry point**

```lua
if vim.g.loaded_puml_viewer then
  return
end
vim.g.loaded_puml_viewer = true

local puml = require("puml-viewer")

vim.api.nvim_create_user_command("PumlPreview", puml.cmd_preview, {
  desc = "Start PlantUML preview server and open browser",
})

vim.api.nvim_create_user_command("PumlExport", puml.cmd_export, {
  nargs = "?",
  complete = function()
    return { "png", "svg" }
  end,
  desc = "Export PlantUML diagram to PNG or SVG",
})

vim.api.nvim_create_user_command("PumlStop", puml.cmd_stop, {
  desc = "Stop PlantUML preview server",
})

local group = vim.api.nvim_create_augroup("PumlViewer", { clear = true })

vim.api.nvim_create_autocmd("BufWritePost", {
  group = group,
  pattern = { "*.puml", "*.plantuml", "*.pu", "*.uml", "*.iuml" },
  callback = function()
    local server = require("puml-viewer.server")
    if server.is_running() then
      local content = table.concat(vim.api.nvim_buf_get_lines(0, 0, -1, false), "\n")
      server.send_update(content)
    end
  end,
  desc = "Send buffer content to PlantUML preview server on save",
})

vim.api.nvim_create_autocmd("VimLeavePre", {
  group = group,
  callback = function()
    local server = require("puml-viewer.server")
    server.stop()
  end,
  desc = "Stop PlantUML preview server on exit",
})
```

Note: autocmd callbacks use `require("puml-viewer.server")` locally to avoid loading the full module tree at startup if the events never fire.

- [ ] **Step 2: Verify commands are registered**

Open Neovim and run:
```vim
:PumlPreview<Tab>
:PumlExport<Tab>
:PumlStop<Tab>
```

All three commands should appear in completion. `:PumlPreview` on a non-puml file should show "not a PlantUML file" warning.

- [ ] **Step 3: Verify setup() override still works**

Open Neovim, run:
```vim
:lua require("puml-viewer").setup({ export_format = "svg" })
:lua print(require("puml-viewer").config.export_format)
```

Expected: `svg`

- [ ] **Step 4: Commit**

```bash
git add plugin/puml-viewer.lua
git commit -m "feat: add plugin/ entry point for auto-loaded commands"
```

---

### Task 4: Create `doc/puml-viewer.txt`

Vimdoc help file. Independent of Tasks 1-3 but written last because it documents the final state.

**Files:**
- Create: `doc/puml-viewer.txt`

- [ ] **Step 1: Create the vimdoc file**

```
*puml-viewer.txt*    PlantUML preview and export for Neovim

Author:  puml-viewer contributors
License: MIT

==============================================================================
CONTENTS                                              *puml-viewer-contents*

    1. Introduction .......................... |puml-viewer-introduction|
    2. Requirements .......................... |puml-viewer-requirements|
    3. Installation .......................... |puml-viewer-installation|
    4. Commands .............................. |puml-viewer-commands|
    5. Configuration ......................... |puml-viewer-configuration|
    6. How It Works .......................... |puml-viewer-how-it-works|
    7. File Types ............................ |puml-viewer-filetypes|

==============================================================================
1. INTRODUCTION                                   *puml-viewer-introduction*

puml-viewer.nvim is a Neovim plugin for working with PlantUML diagrams.
It provides live preview in a browser with auto-reload on save and export
to PNG/SVG.

==============================================================================
2. REQUIREMENTS                                   *puml-viewer-requirements*

- Neovim 0.7+
- Python 3.7+
- PlantUML (e.g. `brew install plantuml`)
- Java (required by PlantUML)

==============================================================================
3. INSTALLATION                                   *puml-viewer-installation*

The plugin works out of the box after installation. Calling `setup()` is
optional and only needed to override default configuration.

Using lazy.nvim: >lua

    {
      "user/puml-viewer.nvim",
      ft = "plantuml",
    }
<

With custom options: >lua

    {
      "user/puml-viewer.nvim",
      ft = "plantuml",
      opts = {
        plantuml_cmd = "/usr/local/bin/plantuml",
        export_format = "svg",
      },
    }
<

Using packer.nvim: >lua

    use "user/puml-viewer.nvim"
<

==============================================================================
4. COMMANDS                                         *puml-viewer-commands*

                                                            *:PumlPreview*
:PumlPreview        Start the preview server and open the diagram in a
                    browser. If the server is already running, re-opens
                    the browser without restarting.

                                                            *:PumlExport*
:PumlExport [{format}]
                    Export the current diagram to a file. {format} is
                    "png" or "svg". Defaults to the configured
                    `export_format` (default: "png").

                                                               *:PumlStop*
:PumlStop           Stop the preview server. Silent no-op if not running.

==============================================================================
5. CONFIGURATION                                *puml-viewer-configuration*

Call `setup()` to override defaults. All options are optional.
                                                          *puml-viewer.setup*
>lua
    require("puml-viewer").setup({
      plantuml_cmd = "plantuml",   -- PlantUML executable or command
      server_port = 0,             -- 0 = auto-detect free port
      browser_cmd = nil,           -- nil = auto-detect (open/xdg-open)
      export_format = "png",       -- default export format: "png" or "svg"
      export_dir = nil,            -- nil = same directory as source file
    })
<

Options:                                           *puml-viewer-options*

`plantuml_cmd`    Command to invoke PlantUML. Default: `"plantuml"`
`server_port`     Port for the preview server. `0` picks a free port
                automatically. Default: `0`
`browser_cmd`     Command to open URLs. `nil` auto-detects `open` (macOS)
                or `xdg-open` (Linux). Default: `nil`
`export_format`   Default format for |:PumlExport|. `"png"` or `"svg"`.
                Default: `"png"`
`export_dir`      Directory for exported files. `nil` uses the same
                directory as the source file. Default: `nil`

==============================================================================
6. HOW IT WORKS                                   *puml-viewer-how-it-works*

Preview: ~

1. `:PumlPreview` spawns a Python HTTP+WebSocket server
2. Browser connects and displays the rendered SVG diagram
3. On file save, buffer content is sent to the server via stdin
4. Server renders SVG using PlantUML and notifies via WebSocket
5. Browser updates the diagram without a full page refresh

Export: ~

1. `:PumlExport` writes buffer content to a temp file
2. Runs PlantUML to produce output in the target format
3. Output is saved next to the source file (or in `export_dir`)
4. Temp file is cleaned up automatically

==============================================================================
7. FILE TYPES                                       *puml-viewer-filetypes*

The plugin recognizes these PlantUML extensions:

    `.puml`         (detected natively by Neovim)
    `.plantuml`     (detected natively by Neovim)
    `.pu`           (added by this plugin)
    `.uml`          (added by this plugin)
    `.iuml`         (added by this plugin)

==============================================================================
vim:tw=78:ts=8:ft=help:norl:
```

- [ ] **Step 2: Generate help tags and verify**

Open Neovim and run:
```vim
:helptags doc/
:help puml-viewer
```

Expected: help file opens with the contents above. Also verify:
```vim
:help :PumlPreview
:help puml-viewer-configuration
```

- [ ] **Step 3: Commit**

```bash
git add doc/puml-viewer.txt
git commit -m "docs: add vimdoc help file for :help puml-viewer"
```

---

### Task 5: Update `README.md`

Remove stale `default_format` option and note that `setup()` is optional.

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update installation section**

Replace the current LazyVim block:
```markdown
### LazyVim

```lua
{
  "user/puml-viewer.nvim",
  ft = "plantuml",
  opts = {},
}
```
```

With:
```markdown
### LazyVim / lazy.nvim

```lua
{
  "user/puml-viewer.nvim",
  ft = "plantuml",
}
```

With custom options:

```lua
{
  "user/puml-viewer.nvim",
  ft = "plantuml",
  opts = {
    plantuml_cmd = "/usr/local/bin/plantuml",
    export_format = "svg",
  },
}
```
```

This removes the separate lazy.nvim section (redundant with LazyVim) and shows that `opts` is optional.

- [ ] **Step 2: Update configuration section**

Replace the current configuration code block:
```lua
require("puml-viewer").setup({
  plantuml_cmd = "plantuml",   -- PlantUML command
  server_port = 0,             -- 0 = auto-detect free port
  browser_cmd = nil,           -- nil = auto-detect (open/xdg-open)
  default_format = "svg",      -- Preview format
  export_format = "png",       -- Default export format ("png" | "svg")
  export_dir = nil,            -- nil = same directory as source file
})
```

With:
```lua
require("puml-viewer").setup({
  plantuml_cmd = "plantuml",   -- PlantUML executable or command
  server_port = 0,             -- 0 = auto-detect free port
  browser_cmd = nil,           -- nil = auto-detect (open/xdg-open)
  export_format = "png",       -- Default export format ("png" | "svg")
  export_dir = nil,            -- nil = same directory as source file
})
```

Removes stale `default_format` line.

- [ ] **Step 3: Add note about optional setup**

Add a line above the configuration code block:

```markdown
Calling `setup()` is optional — the plugin works out of the box with sensible
defaults. Use it only to override specific options:
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for optional setup, remove stale default_format"
```

---

### Task 6: Final verification

Ensure everything works together end-to-end.

- [ ] **Step 1: Run Python server tests**

```bash
python3 -m pytest tests/ -v
```

Expected: all 36 tests pass (server code unchanged).

- [ ] **Step 2: Verify clean Neovim load without setup()**

Open Neovim with no user config loading puml-viewer:
```bash
nvim --clean -u NONE --cmd "set rtp+=." /tmp/test.puml
```

Verify:
```vim
:echo exists(':PumlPreview')
```
Expected: `2` (command exists)

```vim
:echo &filetype
```
Expected: `plantuml`

```vim
:help puml-viewer
```
Expected: help file opens

- [ ] **Step 3: Verify setup() override still works**

```vim
:lua require("puml-viewer").setup({ export_format = "svg" })
:lua print(require("puml-viewer").config.export_format)
```
Expected: `svg`
