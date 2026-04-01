# Interactive Zoom & Pan for Large Diagrams

## Problem

PlantUML generates SVGs with hard-coded pixel dimensions in inline styles
(`style="width:2000px;height:1200px;"`) and sets `preserveAspectRatio="none"`.
The CSS rule `#diagram svg { max-width: 100%; height: auto; }` cannot override
inline styles due to specificity, causing large diagrams to appear squeezed in
the preview window.

## Solution

Interactive zoom + pan with CSS transforms and minimal UI controls.

**Approach:** CSS Transform on inner container (vs. SVG viewBox manipulation or
canvas rendering). Chosen for simplicity, hardware acceleration, and being the
standard pattern used by tools like Figma and Miro.

## Design

### 1. SVG Preparation

After DOMParser sanitization in `fetchDiagram()`, strip inline dimensions and
fix scaling attributes:

```js
const svgEl = doc.documentElement;
svgEl.removeAttribute('width');
svgEl.removeAttribute('height');
svgEl.style.removeProperty('width');
svgEl.style.removeProperty('height');
svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
svgEl.style.width = '100%';
svgEl.style.height = '100%';
```

This removes the root cause — SVG no longer has hard-coded pixel dimensions and
lets the container control sizing.

### 2. Container & Layout

New HTML structure wraps `#diagram` in a fixed-size viewport:

```html
<div id="viewport">
  <div id="diagram"></div>
  <div id="controls">
    <button id="zoom-in" title="Zoom in">+</button>
    <button id="zoom-out" title="Zoom out">−</button>
    <button id="zoom-reset" title="Fit to screen">⊡</button>
  </div>
</div>
```

**Element roles:**

- `#viewport` — white container, fixed size (`95vw` x `calc(100vh - 120px)`),
  `overflow: hidden`, defines the visible area. `cursor: grab`.
- `#diagram` — inner element sized 100% of viewport.
  `transform-origin: 0 0`, receives `transform: scale(s) translate(x, y)`.
- `#controls` — toolbar in bottom-right corner of viewport
  (`position: absolute`), 3 buttons, semi-transparent Catppuccin background.

**Key CSS:**

```css
#viewport {
    position: relative;
    background: #fff;
    border-radius: 8px;
    width: 95vw;
    height: calc(100vh - 120px);
    overflow: hidden;
    cursor: grab;
}
#viewport.grabbing { cursor: grabbing; }
```

No scrollbars — all navigation through zoom + pan.

### 3. Zoom & Pan Logic

**State:**

```js
let scale = 1;
let panX = 0;
let panY = 0;
const MIN_SCALE = 0.1;
const MAX_SCALE = 5;
const ZOOM_FACTOR = 0.1;
```

**Zoom (scroll wheel):**

- `wheel` event on `#viewport`, `e.preventDefault()` to block page scroll
- Zooms toward cursor position (point under cursor stays in place):

```
newScale = clamp(scale * (1 +/- ZOOM_FACTOR), MIN_SCALE, MAX_SCALE)
panX = cursorX - (cursorX - panX) * (newScale / scale)
panY = cursorY - (cursorY - panY) * (newScale / scale)
```

**Pan (mouse drag):**

- `mousedown` on `#viewport` — save start position, set `cursor: grabbing`
- `mousemove` — `panX += deltaX`, `panY += deltaY`
- `mouseup` — end drag, set `cursor: grab`

**Reset (double-click or reset button):**

- `scale = 1, panX = 0, panY = 0` — return to fit-to-viewport

**Zoom buttons (+/-):**

- Zoom toward center of viewport (not cursor, since cursor is on the button)

**Apply transform:**

```js
function applyTransform() {
    diagram.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
}
```

**Reset on new diagram:**

- Each `fetchDiagram()` resets `scale = 1, panX = 0, panY = 0`

### 4. Controls UI

- Bottom-right corner of `#viewport`, `position: absolute`
- Background: `#313244` with 0.8 opacity, `border-radius: 8px`,
  `backdrop-filter: blur(8px)`
- 3 buttons in column: `+`, `-`, reset icon. 32x32px each
- Text color: `#cdd6f4`, hover: `#89b4fa`
- Always visible (discoverability over aesthetics)
- `e.stopPropagation()` on buttons to prevent triggering pan

### 5. Scope

**All changes in one file:** `server/server.py`, within the `INDEX_HTML`
constant (lines 239-370). CSS + HTML + JS inline. No new files.

**Changes:**

1. CSS: new rules for `#viewport`, `#controls`, buttons. Remove old `#diagram`
   max-width/overflow rules.
2. HTML: new `#viewport` wrapper, `#controls` div.
3. JS: SVG preparation step, zoom/pan state, event listeners (wheel, mouse,
   buttons), `applyTransform()`, reset in `fetchDiagram()`.

**Out of scope:**

- Touch events / pinch-to-zoom (not a mobile use case for a Neovim plugin)
- Keyboard shortcuts for zoom
- Zoom level persistence between reloads
- Smooth animations / transitions
