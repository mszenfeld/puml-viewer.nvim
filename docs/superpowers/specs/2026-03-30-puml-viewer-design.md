# puml-viewer.nvim — Design Spec

Neovim plugin for working with PlantUML diagrams. Provides export to PNG/SVG and live browser preview with auto-reload on save. Compatible with LazyVim.

## Decisions

- **Language:** Pure Lua (plugin) + Python (preview server)
- **PlantUML:** Local only, via `plantuml` command (e.g. `brew install plantuml`)
- **Preview server:** Python process spawned by Neovim, HTTP + WebSocket, stdlib only
- **Reload trigger:** `BufWritePost` (on file save)
- **User interface:** Ex commands only (`:PumlPreview`, `:PumlExport`, `:PumlStop`), no default keybindings
- **Configuration:** `require("puml-viewer").setup(opts)`, works with zero config if `plantuml` is in PATH

## File Structure

```
puml-viewer.nvim/
├── lua/
│   └── puml-viewer/
│       ├── init.lua       -- setup(), command registration, autocmds
│       ├── server.lua     -- server process management (start/stop)
│       ├── export.lua     -- PNG/SVG export via plantuml_cmd
│       └── config.lua     -- default config + merge with user opts
└── server/
    └── server.py          -- HTTP + WebSocket server (Python 3.7+, stdlib only)
```

## Configuration

```lua
{
  plantuml_cmd = "plantuml",  -- PlantUML command (default: looks in PATH)
  server_port = 0,            -- 0 = auto-detect free port
  browser_cmd = nil,          -- nil = auto-detect (open/xdg-open), or custom command
  default_format = "svg",     -- format for preview
  export_format = "png",      -- default export format ("png" | "svg")
  export_dir = nil,           -- nil = same directory as source file
}
```

LazyVim usage (zero config):

```lua
{
  "user/puml-viewer.nvim",
  ft = "plantuml",
  opts = {},
}
```

## Ex Commands

| Command                | Action                                                      |
|------------------------|-------------------------------------------------------------|
| `:PumlPreview`         | Start server, render SVG, open browser                      |
| `:PumlExport [png|svg]`| Export diagram to file (defaults to `export_format`)        |
| `:PumlStop`            | Stop preview server                                         |

Behaviors:
- `:PumlPreview` when server already running — re-opens browser, no restart
- `:PumlExport` without argument — uses `export_format` from config
- `:PumlExport svg` — one-time format override
- `:PumlStop` when server not running — silent no-op
- `VimLeavePre` autocmd automatically stops server on exit

Export output path: `<filename_without_extension>.<format>` in the same directory (or `export_dir` if set).

## Data Flow — Preview

1. `BufWritePost *.puml` autocmd sends buffer content to `server.lua`
2. `server.lua` sends content to Python process via stdin (JSON line: `{"type": "update", "content": "..."}`)
3. `server.py` invokes `plantuml_cmd` to generate SVG, keeps result in memory
4. `server.py` serves HTML page with embedded SVG on HTTP, sends `reload` via WebSocket
5. Browser receives `reload`, fetches `/diagram.svg`, replaces innerHTML (no full page reload)

Communication Neovim -> Python: unidirectional via process stdin (JSON lines).
Communication Python -> Neovim: stdout for returning port on startup.

## Data Flow — Export

1. `:PumlExport` saves buffer content to a temp file
2. `export.lua` runs `plantuml_cmd -t<format> -o <output_dir> <tmp_file>` asynchronously via `vim.fn.jobstart()`
3. On completion: `vim.notify()` with output path or error
4. Temp file is cleaned up

## Server (`server.py`)

Single file, ~150-200 lines, Python 3.7+ stdlib only (`asyncio`, `http.server`, `hashlib`).

**HTTP endpoints:**

| Path           | Response                    |
|----------------|-----------------------------|
| `/`            | HTML page with preview      |
| `/diagram.svg` | Current SVG                 |
| `/ws`          | WebSocket upgrade           |

**WebSocket:** Minimal RFC 6455 implementation — handshake (SHA-1 + base64), text frames, close. No fragmentation, binary frames, or ping/pong needed. ~50 lines.

**Lifecycle:**
- On start: prints JSON with port to stdout (`{"port": 12345}`), Lua parses it
- Runs until Neovim closes stdin or sends SIGTERM
- Graceful shutdown: closes WS connections, releases port

## Error Handling

**PlantUML errors:**
- Invalid syntax — stderr from `plantuml_cmd` is sent via WebSocket, browser shows error message (red text) instead of diagram. Neovim gets `vim.notify()` at `WARN` level.

**Server errors:**
- Port busy (manual `server_port`) — `vim.notify()` with error, suggest `server_port = 0`
- Python not found — `vim.notify()` with missing dependency info
- `plantuml_cmd` not found — `vim.notify()` with error

**Validation at `setup()`:**
- Check `plantuml_cmd` exists in PATH (`vim.fn.executable()`)
- Check `python3` is available
- If missing — `vim.notify()` at `ERROR` level, plugin does not load

**Edge cases:**
- `:PumlPreview` on non-`.puml` file — "Not a PlantUML file" message
- `:PumlExport` on empty buffer — no-op with info message

## Dependencies

- **Runtime:** Python 3.7+, Java (for PlantUML), PlantUML (`brew install plantuml` or manual)
- **Neovim:** 0.7+ (for `vim.fn.jobstart()`, `vim.api` autocmds, `vim.notify()`)
- **No pip packages, no luarocks, no npm**

## File Type Detection

Recognized PlantUML extensions: `*.puml`, `*.plantuml`, `*.pu`, `*.uml`, `*.iuml`.

The plugin registers `BufWritePost` autocmd and commands for these filetypes. Neovim already detects `plantuml` filetype for `*.puml` and `*.plantuml`; for others, the plugin adds filetype detection in `setup()`.
