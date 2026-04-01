# Loader for PlantUML Preview

## Problem

When opening the preview (`:PumlPreview`), the browser shows "No diagram yet. Save a .puml file." while PlantUML renders the initial diagram. This message is misleading — the user doesn't need to save anything, rendering is already in progress. The same gap exists on every subsequent reload (after file save), though it's shorter.

## Solution

Replace the placeholder message with a CSS spinner + short text ("Rendering diagram...") that appears before every `fetchDiagram()` call and disappears when the response arrives.

**Approach:** Frontend-only loader (no server protocol changes).

## Design

### Loader element (HTML + CSS)

- New `#loader` div placed as a sibling of `#diagram` (not inside it)
- Contains a CSS-animated spinner (border-based, 32px) and text "Rendering diagram..."
- Catppuccin theme colors: spinner `#89b4fa`, text `#cdd6f4`
- Centered on page with `display: flex; flex-direction: column; align-items: center`
- Animation: `@keyframes spin` — 360deg rotation, 0.8s, linear, infinite
- Visible by default on page load (rendering is already in progress)

### JS show/hide logic

**Show loader (before each fetch):**
- Set `loader.style.display = 'flex'` and `diagram.style.display = 'none'`
- Applies to all three `fetchDiagram()` call sites: initial fetch, WebSocket connect, WebSocket "reload" message

**Hide loader (after fetch completes):**
- In the `.then()` callback: set `loader.style.display = 'none'` and `diagram.style.display = ''`
- Applies to both success (SVG received) and error (ERROR: prefix) branches

### Server placeholder change

- `DiagramState.get_response()`: replace the "No diagram yet..." SVG with a minimal empty SVG
- The browser won't display this SVG to the user (loader is visible), but the endpoint must return valid SVG

## Scope

**Changed file:** `server/server.py` — `INDEX_HTML` template (CSS + JS) and `get_response()` method.

No changes to: WebSocket protocol, Lua plugin code, HTTP endpoints, authentication, or any other server logic.
