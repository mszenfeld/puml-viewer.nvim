# puml-viewer.nvim

Neovim plugin for working with PlantUML diagrams. Live preview in browser with auto-reload on save, export to PNG/SVG.

## Requirements

- Neovim 0.7+
- Python 3.7+
- PlantUML (`brew install plantuml`)
- Java (required by PlantUML)

## Installation

### LazyVim

```lua
{
  "user/puml-viewer.nvim",
  ft = "plantuml",
  opts = {},
}
```

### lazy.nvim

```lua
{
  "user/puml-viewer.nvim",
  ft = "plantuml",
  config = function()
    require("puml-viewer").setup()
  end,
}
```

## Usage

| Command                | Description                                |
|------------------------|--------------------------------------------|
| `:PumlPreview`         | Start preview server and open browser      |
| `:PumlExport [png|svg]`| Export diagram (default: png)              |
| `:PumlStop`            | Stop preview server                        |

The preview auto-reloads when you save the file (`:w`).

## Configuration

All options are optional — the plugin works out of the box if `plantuml` is in your PATH.

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

## How It Works

1. `:PumlPreview` spawns a Python HTTP+WebSocket server in the background
2. Browser connects and displays the rendered SVG diagram
3. On file save, buffer content is sent to the server via stdin
4. Server renders SVG using `plantuml` and broadcasts reload via WebSocket
5. Browser updates the diagram without a full page refresh

## Supported File Extensions

`*.puml`, `*.plantuml`, `*.pu`, `*.uml`, `*.iuml`
