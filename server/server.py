#!/usr/bin/env python3
"""PlantUML preview server with HTTP and WebSocket support.

Spawned by the puml-viewer.nvim Neovim plugin. Reads JSON lines from stdin,
renders PlantUML diagrams to SVG, and serves a live preview page with
WebSocket-based auto-reload.

Dependencies: Python 3.7+ stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shlex
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BufferedIOBase
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# WebSocket helpers (minimal RFC 6455)
# ---------------------------------------------------------------------------

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_WS_PAYLOAD = 65536  # 64 KB -- more than enough for this use case


def ws_accept_key(client_key: str) -> str:
    """Compute WebSocket accept key per RFC 6455 Section 4.2.2."""
    sha1 = hashlib.sha1((client_key + WS_MAGIC).encode()).digest()
    return base64.b64encode(sha1).decode()


class WebSocketClient:
    """Minimal WebSocket connection handler (server side)."""

    def __init__(self, rfile: BufferedIOBase, wfile: BufferedIOBase) -> None:
        self.rfile = rfile
        self.wfile = wfile
        self.closed: bool = False

    def send_text(self, text: str) -> None:
        """Send a text frame to the client."""
        payload = text.encode("utf-8")
        frame = bytearray([0x81])  # FIN + text opcode

        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, "big"))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, "big"))

        frame.extend(payload)
        try:
            self.wfile.write(bytes(frame))
            self.wfile.flush()
        except (OSError, ValueError):
            self.closed = True

    def read_frame(self) -> str | None:
        """Read a WebSocket frame. Returns text content or None on close/error."""
        try:
            b1 = self.rfile.read(1)
            if not b1:
                return None

            opcode = b1[0] & 0x0F

            b2 = self.rfile.read(1)
            masked = bool(b2[0] & 0x80)
            length = b2[0] & 0x7F

            if length == 126:
                length = int.from_bytes(self.rfile.read(2), "big")
            elif length == 127:
                length = int.from_bytes(self.rfile.read(8), "big")

            if length > MAX_WS_PAYLOAD:
                return None  # reject oversized frames (CWE-400)

            mask_key = self.rfile.read(4) if masked else b""
            payload = bytearray(self.rfile.read(length))

            if masked:
                for i in range(len(payload)):
                    payload[i] ^= mask_key[i % 4]

            if opcode == 0x8:  # close
                return None
            if opcode == 0x1:  # text
                return payload.decode("utf-8")
            return ""
        except (OSError, IndexError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Diagram state
# ---------------------------------------------------------------------------

MAX_WS_CLIENTS = 10  # cap concurrent WebSocket connections (CWE-770)


class DiagramState:
    """Thread-safe container for the current diagram SVG and error state."""

    def __init__(self) -> None:
        self.svg_content: str | None = None
        self.error: str | None = None
        self._ws_clients: list[WebSocketClient] = []
        self._lock = threading.Lock()

    def set_svg(self, content: str) -> None:
        with self._lock:
            self.svg_content = content
            self.error = None

    def set_error(self, error_msg: str) -> None:
        with self._lock:
            self.error = error_msg
            self.svg_content = None

    def get_response(self) -> str:
        with self._lock:
            if self.error:
                return f"ERROR:{self.error}"
            if self.svg_content:
                return self.svg_content
            return '<svg xmlns="http://www.w3.org/2000/svg"/>'

    def add_client(self, client: WebSocketClient) -> None:
        """Register a WebSocket client (thread-safe).

        Silently rejects connections once MAX_WS_CLIENTS is reached to prevent
        unbounded resource allocation (CWE-770).
        """
        with self._lock:
            if len(self._ws_clients) >= MAX_WS_CLIENTS:
                return
            self._ws_clients.append(client)

    def remove_client(self, client: WebSocketClient) -> None:
        """Unregister a WebSocket client (thread-safe)."""
        with self._lock:
            if client in self._ws_clients:
                self._ws_clients.remove(client)

    def broadcast(self, message: str) -> None:
        """Send a message to all connected WebSocket clients (thread-safe).

        Dead clients discovered during broadcast are automatically removed.
        """
        with self._lock:
            clients = list(self._ws_clients)
        dead: list[WebSocketClient] = []
        for client in clients:
            try:
                client.send_text(message)
            except (OSError, ValueError):
                dead.append(client)
        if dead:
            with self._lock:
                for c in dead:
                    if c in self._ws_clients:
                        self._ws_clients.remove(c)


# Global state instance used by the running server
_state = DiagramState()

# Session token for authenticating HTTP requests (CWE-306)
_session_token: str = secrets.token_urlsafe(32)


def _broadcast_reload(state: DiagramState) -> None:
    """Send reload message to all connected WebSocket clients."""
    state.broadcast("reload")


# ---------------------------------------------------------------------------
# PlantUML rendering
# ---------------------------------------------------------------------------


def render_plantuml(
    puml_content: str,
    plantuml_cmd: str = "plantuml",
    source_path: str | None = None,
) -> tuple[str | None, str | None]:
    """Render PlantUML content to SVG using pipe mode (stdin→stdout).

    Args:
        puml_content: PlantUML source text.
        plantuml_cmd: Command to invoke PlantUML (may contain spaces for
            multi-word commands like "java -jar plantuml.jar").
        source_path: Original file path. When provided, the subprocess runs
            with cwd set to its parent directory so ``!include`` directives
            with relative paths resolve correctly.

    Returns:
        Tuple of (svg_string, error_string). One will always be None.
    """
    if not puml_content.strip():
        return None, "Buffer is empty"

    try:
        cmd = shlex.split(plantuml_cmd) + ["-tsvg", "-pipe"]
        cwd = os.path.dirname(source_path) if source_path else None
        result = subprocess.run(
            cmd, input=puml_content, capture_output=True, text=True, timeout=10,
            cwd=cwd,
        )

        if result.returncode != 0:
            return None, result.stderr.strip() or "PlantUML rendering failed"

        if not result.stdout.strip():
            return None, "No SVG output from PlantUML"

        return result.stdout, None

    except subprocess.TimeoutExpired:
        return None, "PlantUML rendering timed out (>10s)"
    except FileNotFoundError:
        return None, f"PlantUML command not found: {plantuml_cmd}"
    except OSError as e:
        return None, f"Error rendering PlantUML: {e}"


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link rel="icon" href="data:,">
    <title>PlantUML Preview</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1e1e2e; color: #cdd6f4; min-height: 100vh;
            display: flex; flex-direction: column; align-items: center;
            padding: 20px;
        }
        h1 { font-size: 1.2rem; color: #89b4fa; margin-bottom: 16px; }
        #status {
            font-size: 0.8rem; padding: 4px 12px; border-radius: 12px;
            margin-bottom: 16px;
        }
        .connected { background: #1e3a2e; color: #a6e3a1; }
        .disconnected { background: #3e1e1e; color: #f38ba8; }
        #error {
            color: #f38ba8; background: #3e1e2e; padding: 12px 16px;
            border-radius: 8px; margin-bottom: 16px; display: none;
            font-family: monospace; font-size: 0.85rem; max-width: 90vw;
            white-space: pre-wrap;
        }
        #loader {
            position: absolute; inset: 0;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 12px;
            background: #1e1e2e; z-index: 5;
        }
        #loader-spinner {
            width: 32px; height: 32px; border: 3px solid #313244;
            border-top-color: #89b4fa; border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        #loader-text {
            font-size: 0.9rem; color: #cdd6f4;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
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
        #diagram {
            width: 100%;
            height: 100%;
            transform-origin: 0 0;
        }
        #diagram svg {
            width: 100%;
            height: 100%;
        }
        #controls {
            position: absolute;
            bottom: 16px;
            right: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            background: rgba(49, 50, 68, 0.8);
            border-radius: 8px;
            padding: 8px;
            backdrop-filter: blur(8px);
            z-index: 10;
        }
        #controls button {
            width: 32px;
            height: 32px;
            padding: 0;
            border: none;
            border-radius: 4px;
            background: transparent;
            color: #cdd6f4;
            font-size: 16px;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        #controls button:hover {
            background: rgba(137, 180, 250, 0.2);
            color: #89b4fa;
        }
        #controls button:active {
            background: rgba(137, 180, 250, 0.4);
        }
    </style>
</head>
<body>
    <h1>PlantUML Preview</h1>
    <div id="status" class="disconnected">disconnected</div>
    <div id="error"></div>
    <div id="viewport">
        <div id="loader">
            <div id="loader-spinner"></div>
            <div id="loader-text">Rendering diagram...</div>
        </div>
        <div id="diagram"></div>
        <div id="controls">
            <button id="zoom-in" title="Zoom in">+</button>
            <button id="zoom-out" title="Zoom out">&minus;</button>
            <button id="zoom-reset" title="Fit to screen">&#x22A1;</button>
        </div>
    </div>
    <script>
        const statusEl = document.getElementById('status');
        const errorEl = document.getElementById('error');
        const diagramEl = document.getElementById('diagram');
        const loaderEl = document.getElementById('loader');

        // Zoom/pan state
        const viewportEl = document.getElementById('viewport');
        let scale = 1;
        let panX = 0;
        let panY = 0;
        const MIN_SCALE = 0.1;
        const MAX_SCALE = 5;
        const ZOOM_FACTOR = 0.1;
        let isPanning = false;
        let panStartX = 0;
        let panStartY = 0;

        function applyTransform() {
            diagramEl.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
        }

        function clamp(value, min, max) {
            return Math.max(min, Math.min(max, value));
        }

        function resetZoom() {
            scale = 1;
            panX = 0;
            panY = 0;
            applyTransform();
        }

        // Strip the token from the URL bar so it no longer appears in
        // browser history or the address bar (CWE-598). The server set a
        // session cookie during this page load, so subsequent fetches
        // authenticate via that cookie instead.
        if (location.search.includes('token=')) {
            const clean = location.pathname;
            history.replaceState(null, '', clean);
        }

        function fetchDiagram() {
            loaderEl.style.display = 'flex';
            resetZoom();
            diagramEl.style.display = 'none';
            fetch('/diagram.svg', {credentials: 'same-origin'})
                .then(r => {
                    if (r.status === 403) throw new Error('Forbidden');
                    return r.text();
                })
                .then(text => {
                    loaderEl.style.display = 'none';
                    diagramEl.style.display = 'block';
                    if (text.startsWith('ERROR:')) {
                        errorEl.textContent = text.substring(6);
                        errorEl.style.display = 'block';
                        diagramEl.replaceChildren();
                    } else {
                        errorEl.style.display = 'none';
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(text, 'image/svg+xml');
                        doc.querySelectorAll('script, foreignObject, animate, set').forEach(el => el.remove());
                        doc.querySelectorAll('*').forEach(el => {
                            for (const attr of [...el.attributes]) {
                                if (attr.name.startsWith('on') ||
                                    (attr.value && attr.value.trim().toLowerCase().startsWith('javascript:'))) {
                                    el.removeAttribute(attr.name);
                                }
                            }
                        });
                        const svgEl = doc.documentElement;
                        svgEl.removeAttribute('width');
                        svgEl.removeAttribute('height');
                        svgEl.style.removeProperty('width');
                        svgEl.style.removeProperty('height');
                        svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
                        svgEl.style.width = '100%';
                        svgEl.style.height = '100%';
                        diagramEl.replaceChildren(doc.documentElement);
                    }
                })
                .catch(e => {
                    loaderEl.style.display = 'none';
                    diagramEl.style.display = 'block';
                    errorEl.textContent = 'Connection error: ' + e.message;
                    errorEl.style.display = 'block';
                    console.error('Fetch error:', e);
                });
        }

        viewportEl.addEventListener('wheel', (e) => {
            e.preventDefault();
            const rect = viewportEl.getBoundingClientRect();
            const cursorX = e.clientX - rect.left;
            const cursorY = e.clientY - rect.top;
            const oldScale = scale;
            const zoomDirection = e.deltaY > 0 ? 1 : -1;
            scale = clamp(scale * (1 - zoomDirection * ZOOM_FACTOR), MIN_SCALE, MAX_SCALE);
            panX = cursorX - (cursorX - panX) * (scale / oldScale);
            panY = cursorY - (cursorY - panY) * (scale / oldScale);
            applyTransform();
        }, { passive: false });

        viewportEl.addEventListener('mousedown', (e) => {
            if (e.target.closest('#controls')) return;
            isPanning = true;
            panStartX = e.clientX;
            panStartY = e.clientY;
            viewportEl.classList.add('grabbing');
        });

        document.addEventListener('mousemove', (e) => {
            if (!isPanning) return;
            panX += e.clientX - panStartX;
            panY += e.clientY - panStartY;
            panStartX = e.clientX;
            panStartY = e.clientY;
            applyTransform();
        });

        document.addEventListener('mouseup', () => {
            if (isPanning) {
                isPanning = false;
                viewportEl.classList.remove('grabbing');
            }
        });

        viewportEl.addEventListener('dblclick', (e) => {
            if (e.target.closest('#controls')) return;
            resetZoom();
        });

        function zoomTowardCenter(direction) {
            const rect = viewportEl.getBoundingClientRect();
            const cx = rect.width / 2;
            const cy = rect.height / 2;
            const oldScale = scale;
            scale = clamp(scale * (1 + direction * ZOOM_FACTOR), MIN_SCALE, MAX_SCALE);
            panX = cx - (cx - panX) * (scale / oldScale);
            panY = cy - (cy - panY) * (scale / oldScale);
            applyTransform();
        }

        document.getElementById('zoom-in').addEventListener('click', (e) => {
            e.stopPropagation();
            zoomTowardCenter(1);
        });

        document.getElementById('zoom-out').addEventListener('click', (e) => {
            e.stopPropagation();
            zoomTowardCenter(-1);
        });

        document.getElementById('zoom-reset').addEventListener('click', (e) => {
            e.stopPropagation();
            resetZoom();
        });

        function connect() {
            const ws = new WebSocket('ws://' + location.host + '/ws');
            ws.onopen = () => {
                statusEl.textContent = 'connected';
                statusEl.className = 'connected';
                fetchDiagram();
            };
            ws.onmessage = (e) => { if (e.data === 'reload') fetchDiagram(); };
            ws.onclose = () => {
                statusEl.textContent = 'disconnected';
                statusEl.className = 'disconnected';
                setTimeout(connect, 2000);
            };
            ws.onerror = () => ws.close();
        }

        connect();
    </script>
</body>
</html>"""


class PumlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for PlantUML preview server."""

    # Hide Python version from Server header (CWE-200)
    server_version = "PumlViewer"
    sys_version = ""

    # Subclasses can override to inject their own state/token (used in tests)
    _state: DiagramState | None = None
    _token: str | None = None

    @property
    def state(self) -> DiagramState:
        return self._state if self._state is not None else _state

    @property
    def session_token(self) -> str:
        return self._token if self._token is not None else _session_token

    def end_headers(self) -> None:
        """Inject security headers on every response (CWE-693)."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def _check_token(self) -> bool:
        """Validate session token from query string or session cookie.

        Accepts authentication via:
        1. ``?token=...`` query parameter (used for initial page load), or
        2. ``puml_session`` cookie (set after the first authenticated request).

        This avoids keeping the token in URLs after the first load (CWE-598).
        Returns True if valid.
        """
        qs = parse_qs(urlparse(self.path).query)
        token = qs.get("token", [None])[0]
        if token == self.session_token:
            return True

        # Fall back to cookie-based auth
        cookie_header = self.headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("puml_session="):
                cookie_value = part[len("puml_session="):]
                if cookie_value == self.session_token:
                    return True

        self.send_error(403, "Forbidden: invalid or missing session token")
        return False

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path).path
        if parsed_path == "/":
            if not self._check_token():
                return
            self._serve_html()
        elif parsed_path == "/diagram.svg":
            if not self._check_token():
                return
            self._serve_diagram()
        elif parsed_path == "/ws":
            self._handle_ws()
        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        body = INDEX_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'unsafe-inline' 'wasm-unsafe-eval'; "
            "connect-src 'self' ws://localhost:* ws://127.0.0.1:*; "
            "style-src 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com",
        )
        # Set session cookie so subsequent requests don't need the token in
        # the URL (CWE-598). HttpOnly prevents JS access; SameSite=Strict
        # limits the cookie to same-origin requests.
        self.send_header(
            "Set-Cookie",
            f"puml_session={self.session_token}; HttpOnly; SameSite=Strict; Path=/",
        )
        self.end_headers()
        self.wfile.write(body)

    def _serve_diagram(self) -> None:
        body = self.state.get_response().encode()
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_ws(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
            self.send_error(403, "Forbidden origin")
            return

        if not self._check_token():
            return

        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400, "Missing Sec-WebSocket-Key")
            return

        accept = ws_accept_key(key)
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        client = WebSocketClient(self.rfile, self.wfile)
        self.state.add_client(client)

        try:
            while not client.closed:
                frame = client.read_frame()
                if frame is None:
                    break
        except OSError:
            pass
        finally:
            self.state.remove_client(client)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default HTTP logging."""


# ---------------------------------------------------------------------------
# Stdin reader (receives updates from Neovim)
# ---------------------------------------------------------------------------


def read_stdin(state: DiagramState, plantuml_cmd: str) -> None:
    """Read JSON lines from stdin and render PlantUML diagrams."""
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                state.set_error(f"JSON parse error: {e}")
                _broadcast_reload(state)
                continue

            if msg.get("type") == "update":
                content = msg.get("content", "")
                filepath = msg.get("filepath")
                if not content.strip():
                    state.set_error("Buffer is empty")
                else:
                    svg, error = render_plantuml(
                        content, plantuml_cmd, source_path=filepath
                    )
                    if error:
                        state.set_error(error)
                    elif svg:
                        state.set_svg(svg)
                    else:
                        state.set_error("Unexpected: no SVG and no error")
                _broadcast_reload(state)
    except (KeyboardInterrupt, BrokenPipeError):
        pass


# ---------------------------------------------------------------------------
# CLI and entry point
# ---------------------------------------------------------------------------


def find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="PlantUML preview server")
    parser.add_argument(
        "--plantuml-cmd",
        default="plantuml",
        help="PlantUML command (default: plantuml)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Server port (default: 0 = auto)",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Start the preview server."""
    args = parse_args()

    port = args.port if args.port != 0 else find_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), PumlHandler)

    # Tell Neovim the port and session token via stdout
    print(json.dumps({"port": port, "token": _session_token}), flush=True)

    # Read stdin in background thread
    stdin_thread = threading.Thread(
        target=read_stdin, args=(_state, args.plantuml_cmd), daemon=True
    )
    stdin_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
