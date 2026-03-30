"""Tests for HTTP server endpoints."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from typing import Generator

import pytest

from server.server import DiagramState, HTTPServer, PumlHandler, find_free_port


class TestFindFreePort:
    """Test free port discovery."""

    def test_returns_positive_integer(self) -> None:
        port = find_free_port()

        assert isinstance(port, int)
        assert port > 0

    def test_returns_different_ports_on_successive_calls(self) -> None:
        port_a = find_free_port()
        port_b = find_free_port()

        # Not guaranteed to differ, but extremely likely
        assert isinstance(port_a, int)
        assert isinstance(port_b, int)


class TestHttpEndpoints:
    """Integration tests for HTTP endpoints."""

    @pytest.fixture()
    def server_with_state(self) -> Generator[tuple[HTTPConnection, DiagramState], None, None]:
        """Start a real HTTP server on a free port and return connection + state."""
        port = find_free_port()
        state = DiagramState()

        # Inject state into handler via closure
        class TestHandler(PumlHandler):
            _state = state

        server = HTTPServer(("127.0.0.1", port), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        time.sleep(0.1)  # Let server start

        conn = HTTPConnection("127.0.0.1", port, timeout=5)

        yield conn, state

        server.shutdown()
        conn.close()

    def test_index_returns_html(
        self, server_with_state: tuple[HTTPConnection, DiagramState]
    ) -> None:
        conn, _ = server_with_state

        conn.request("GET", "/")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert "text/html" in response.getheader("Content-Type", "")
        assert "PlantUML Preview" in body

    def test_diagram_returns_placeholder_when_empty(
        self, server_with_state: tuple[HTTPConnection, DiagramState]
    ) -> None:
        conn, _ = server_with_state

        conn.request("GET", "/diagram.svg")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert "No diagram yet" in body

    def test_diagram_returns_svg_content(
        self, server_with_state: tuple[HTTPConnection, DiagramState]
    ) -> None:
        conn, state = server_with_state
        state.set_svg("<svg><circle/></svg>")

        conn.request("GET", "/diagram.svg")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert body == "<svg><circle/></svg>"

    def test_diagram_returns_error_when_set(
        self, server_with_state: tuple[HTTPConnection, DiagramState]
    ) -> None:
        conn, state = server_with_state
        state.set_error("Bad syntax")

        conn.request("GET", "/diagram.svg")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert body.startswith("ERROR:")
        assert "Bad syntax" in body

    def test_unknown_path_returns_404(
        self, server_with_state: tuple[HTTPConnection, DiagramState]
    ) -> None:
        conn, _ = server_with_state

        conn.request("GET", "/nonexistent")
        response = conn.getresponse()

        assert response.status == 404


class TestParseArgs:
    """Test CLI argument parsing."""

    def test_default_values(self) -> None:
        from server.server import parse_args

        args = parse_args([])

        assert args.plantuml_cmd == "plantuml"
        assert args.port == 0

    def test_custom_plantuml_cmd(self) -> None:
        from server.server import parse_args

        args = parse_args(["--plantuml-cmd", "java -jar plantuml.jar"])

        assert args.plantuml_cmd == "java -jar plantuml.jar"

    def test_custom_port(self) -> None:
        from server.server import parse_args

        args = parse_args(["--port", "8080"])

        assert args.port == 8080
