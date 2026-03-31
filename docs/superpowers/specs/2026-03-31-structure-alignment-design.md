# puml-viewer.nvim — Structure Alignment Design

Align repository structure with Neovim plugin conventions: add `plugin/`, `ftdetect/`, `doc/` directories, make `setup()` optional, and move to lazy dependency validation.

## Decisions

- **`setup()` optional** — commands work out of the box with sensible defaults; `setup(opts)` only overrides config
- **Lazy validation** — `python3`/`plantuml` checked at command invocation, not at load time
- **vimdoc** — `doc/puml-viewer.txt` for `:help puml-viewer`
- **ftdetect** — register `.pu`, `.uml`, `.iuml` extensions (Neovim handles `.puml`/`.plantuml` natively)
- **No changes** to `server.lua`, `export.lua`, `config.lua`, `utils.lua`, `server.py`

## New Files

### `plugin/puml-viewer.lua`

Auto-loaded entry point. Responsibilities:

1. Guard with `vim.g.loaded_puml_viewer` to prevent double-loading
2. Register Ex commands: `:PumlPreview`, `:PumlExport`, `:PumlStop`
3. Register autocommands: `BufWritePost` (send update), `VimLeavePre` (stop server)
4. Commands read config lazily via `require("puml-viewer").config` — always reflects latest state, including after `setup()` call

Dependency validation (`python3`, `plantuml`) happens inside command handlers, not at load time. If a dependency is missing, the user gets a `vim.notify()` error when they try to use the command — not at Neovim startup.

### `ftdetect/plantuml.lua`

Registers additional PlantUML file extensions via `vim.filetype.add()`:

```lua
vim.filetype.add({
  extension = {
    pu = "plantuml",
    uml = "plantuml",
    iuml = "plantuml",
  },
})
```

Only non-native extensions. Neovim already detects `.puml` and `.plantuml`.

### `doc/puml-viewer.txt`

Vimdoc help file covering:

- Plugin description and requirements
- Installation (lazy.nvim, LazyVim, packer)
- Commands (`:PumlPreview`, `:PumlExport`, `:PumlStop`)
- Configuration (`setup()` optional, all options with defaults)
- How it works (preview data flow, export data flow)
- Recognized file extensions

Content mirrors README but in vimdoc format with proper tags for `:help` navigation.

## Modified Files

### `lua/puml-viewer/init.lua`

Changes:

- **Remove** `register_commands()` — moved to `plugin/puml-viewer.lua`
- **Remove** `register_autocmds()` — moved to `plugin/puml-viewer.lua`
- **Remove** `vim.filetype.add()` from `setup()` — moved to `ftdetect/plantuml.lua`
- **Remove** `validate_dependencies()` call from `setup()` — validation moves to command handlers
- **Keep** `validate_dependencies()` function itself — still used, but called lazily from command handlers
- **Keep** `detect_browser_cmd()`, `open_preview()`, `cmd_preview()`, `cmd_export()`, `cmd_stop()` — still the command logic, called from `plugin/`
- **Add** `M.config` field initialized with defaults — `setup()` only merges user opts into it
- **Expose** command handler functions (`M.cmd_preview`, `M.cmd_export`, `M.cmd_stop`) so `plugin/` can reference them

### `README.md`

- Remove stale `default_format` option from configuration example (already removed from code)
- Update installation section to note that `setup()` is optional

## Unchanged Files

- `lua/puml-viewer/config.lua`
- `lua/puml-viewer/server.lua`
- `lua/puml-viewer/export.lua`
- `lua/puml-viewer/utils.lua`
- `server/server.py`
- `tests/*`

## Target Structure

```
puml-viewer.nvim/
├── plugin/
│   └── puml-viewer.lua        -- auto-loaded: commands + autocmds
├── ftdetect/
│   └── plantuml.lua           -- filetype detection for .pu/.uml/.iuml
├── doc/
│   └── puml-viewer.txt        -- vimdoc help
├── lua/
│   └── puml-viewer/
│       ├── init.lua           -- setup() (optional), command logic, config
│       ├── config.lua         -- default config + merge
│       ├── server.lua         -- server process management
│       ├── export.lua         -- PNG/SVG export
│       └── utils.lua          -- shared utilities
├── server/
│   └── server.py              -- HTTP + WebSocket server
└── tests/
    ├── conftest.py
    ├── test_http.py
    ├── test_rendering.py
    ├── test_state.py
    └── test_websocket.py
```
