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
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
# WebSocket helpers (minimal RFC 6455)
# ---------------------------------------------------------------------------

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept_key(client_key: str) -> str:
    """Compute WebSocket accept key per RFC 6455 Section 4.2.2."""
    sha1 = hashlib.sha1((client_key + WS_MAGIC).encode()).digest()
    return base64.b64encode(sha1).decode()


class WebSocketClient:
    """Minimal WebSocket connection handler (server side)."""

    def __init__(self, rfile: object, wfile: object) -> None:
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


class DiagramState:
    """Thread-safe container for the current diagram SVG and error state."""

    def __init__(self) -> None:
        self.svg_content: str | None = None
        self.error: str | None = None
        self.ws_clients: list[WebSocketClient] = []
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
            return (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                "<text y=\"20\">No diagram yet. Save a .puml file.</text>"
                "</svg>"
            )


# Global state instance used by the running server
_state = DiagramState()


def _broadcast_reload(state: DiagramState) -> None:
    """Send reload message to all connected WebSocket clients."""
    dead: list[WebSocketClient] = []
    for client in list(state.ws_clients):
        try:
            client.send_text("reload")
        except (OSError, ValueError):
            dead.append(client)
    for client in dead:
        if client in state.ws_clients:
            state.ws_clients.remove(client)


# ---------------------------------------------------------------------------
# PlantUML rendering
# ---------------------------------------------------------------------------


def render_plantuml(puml_content: str, plantuml_cmd: str = "plantuml") -> tuple[str | None, str | None]:
    """Render PlantUML content to SVG.

    Args:
        puml_content: PlantUML source text.
        plantuml_cmd: Command to invoke PlantUML (may contain spaces for
            multi-word commands like "java -jar plantuml.jar").

    Returns:
        Tuple of (svg_string, error_string). One will always be None.
    """
    if not puml_content.strip():
        return None, "Buffer is empty"

    try:
        fd, temp_path = tempfile.mkstemp(suffix=".puml")
        temp_file = Path(temp_path)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(puml_content)

            cmd = plantuml_cmd.split() + [
                "-tsvg",
                "-o",
                str(temp_file.parent),
                str(temp_file),
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                return None, result.stderr.strip() or "PlantUML rendering failed"

            svg_file = temp_file.with_suffix(".svg")
            if svg_file.exists():
                svg_content = svg_file.read_text()
                svg_file.unlink()
                return svg_content, None

            return None, "No SVG file generated"
        finally:
            if temp_file.exists():
                temp_file.unlink()

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
        #diagram {
            background: #fff; border-radius: 8px; padding: 16px;
            max-width: 95vw; overflow: auto;
        }
        #diagram svg { max-width: 100%; height: auto; }
    </style>
</head>
<body>
    <h1>PlantUML Preview</h1>
    <div id="status" class="disconnected">disconnected</div>
    <div id="error"></div>
    <div id="diagram"></div>
    <script>
        const statusEl = document.getElementById('status');
        const errorEl = document.getElementById('error');
        const diagramEl = document.getElementById('diagram');

        function fetchDiagram() {
            fetch('/diagram.svg')
                .then(r => r.text())
                .then(text => {
                    if (text.startsWith('ERROR:')) {
                        errorEl.textContent = text.substring(6);
                        errorEl.style.display = 'block';
                        diagramEl.innerHTML = '';
                    } else {
                        errorEl.style.display = 'none';
                        diagramEl.innerHTML = text;
                    }
                })
                .catch(e => console.error('Fetch error:', e));
        }

        function connect() {
            const ws = new WebSocket('ws://' + location.host + '/ws');
            ws.onopen = () => {
                statusEl.textContent = 'connected';
                statusEl.className = 'connected';
            };
            ws.onmessage = (e) => { if (e.data === 'reload') fetchDiagram(); };
            ws.onclose = () => {
                statusEl.textContent = 'disconnected';
                statusEl.className = 'disconnected';
                setTimeout(connect, 2000);
            };
            ws.onerror = () => ws.close();
        }

        fetchDiagram();
        connect();
    </script>
</body>
</html>"""


class PumlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for PlantUML preview server."""

    # Subclasses can override to inject their own state (used in tests)
    _state: DiagramState | None = None

    @property
    def state(self) -> DiagramState:
        return self._state if self._state is not None else _state

    def do_GET(self) -> None:
        if self.path == "/":
            self._serve_html()
        elif self.path == "/diagram.svg":
            self._serve_diagram()
        elif self.path == "/ws":
            self._handle_ws()
        else:
            self.send_error(404)

    def _serve_html(self) -> None:
        body = INDEX_HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        self.state.ws_clients.append(client)

        try:
            while not client.closed:
                frame = client.read_frame()
                if frame is None:
                    break
        except OSError:
            pass
        finally:
            if client in self.state.ws_clients:
                self.state.ws_clients.remove(client)

    def log_message(self, format: str, *args: object) -> None:
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
                if not content.strip():
                    state.set_error("Buffer is empty")
                else:
                    svg, error = render_plantuml(content, plantuml_cmd)
                    if error:
                        state.set_error(error)
                    else:
                        state.set_svg(svg)
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

    # Tell Neovim the port via stdout
    print(json.dumps({"port": port}), flush=True)

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
