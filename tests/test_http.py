"""Tests for HTTP server endpoints."""

from __future__ import annotations

import threading
import time
from http.client import HTTPConnection
from collections.abc import Generator

import pytest

from server.server import DiagramState, PumlHandler, ThreadingHTTPServer, find_free_port

# Fixed test token used across all test fixtures
_TEST_TOKEN = "test-token-for-http-tests"


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
    def server_with_state(
        self,
    ) -> Generator[tuple[HTTPConnection, DiagramState, str], None, None]:
        """Start a real HTTP server on a free port.

        Yields (connection, state, token).
        """
        port = find_free_port()
        state = DiagramState()
        token = _TEST_TOKEN

        # Inject state and token into handler via closure
        class TestHandler(PumlHandler):
            _state = state
            _token = token

        server = ThreadingHTTPServer(("127.0.0.1", port), TestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        time.sleep(0.1)  # Let server start

        conn = HTTPConnection("127.0.0.1", port, timeout=5)

        yield conn, state, token

        server.shutdown()
        conn.close()

    def test_index_returns_html(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, token = server_with_state

        conn.request("GET", f"/?token={token}")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert "text/html" in response.getheader("Content-Type", "")
        assert "PlantUML Preview" in body

    def test_index_rejected_without_token(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, _ = server_with_state

        conn.request("GET", "/")
        response = conn.getresponse()
        response.read()

        assert response.status == 403

    def test_index_rejected_with_wrong_token(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, _ = server_with_state

        conn.request("GET", "/?token=wrong-token")
        response = conn.getresponse()
        response.read()

        assert response.status == 403

    def test_diagram_returns_empty_svg_when_empty(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, token = server_with_state

        conn.request("GET", f"/diagram.svg?token={token}")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert body == '<svg xmlns="http://www.w3.org/2000/svg"/>'

    def test_diagram_returns_svg_content(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, state, token = server_with_state
        state.set_svg("<svg><circle/></svg>")

        conn.request("GET", f"/diagram.svg?token={token}")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert body == "<svg><circle/></svg>"

    def test_diagram_returns_error_when_set(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, state, token = server_with_state
        state.set_error("Bad syntax")

        conn.request("GET", f"/diagram.svg?token={token}")
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert body.startswith("ERROR:")
        assert "Bad syntax" in body

    def test_diagram_rejected_without_token(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, _ = server_with_state

        conn.request("GET", "/diagram.svg")
        response = conn.getresponse()
        response.read()

        assert response.status == 403

    def test_index_csp_allows_data_images(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, token = server_with_state

        conn.request("GET", f"/?token={token}")
        response = conn.getresponse()
        response.read()

        csp = response.getheader("Content-Security-Policy", "")
        # PlantUML embeds sprites as data:image/png;base64 inside the SVG;
        # CSP must allow data: in img-src or they render as broken images.
        assert "img-src" in csp
        assert "data:" in csp.split("img-src", 1)[1].split(";", 1)[0]

    def test_index_sets_session_cookie(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, token = server_with_state

        conn.request("GET", f"/?token={token}")
        response = conn.getresponse()
        response.read()

        set_cookie = response.getheader("Set-Cookie", "")
        assert "puml_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=Strict" in set_cookie

    def test_diagram_accessible_via_session_cookie(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, state, token = server_with_state
        state.set_svg("<svg><rect/></svg>")

        # First request: authenticate with token, receive cookie
        conn.request("GET", f"/?token={token}")
        response = conn.getresponse()
        response.read()
        set_cookie = response.getheader("Set-Cookie", "")
        # Extract just the cookie value (before any attributes)
        cookie = set_cookie.split(";")[0].strip()

        # Second request: authenticate with cookie only (no token in URL)
        conn.request("GET", "/diagram.svg", headers={"Cookie": cookie})
        response = conn.getresponse()
        body = response.read().decode()

        assert response.status == 200
        assert body == "<svg><rect/></svg>"

    def test_diagram_rejected_with_wrong_cookie(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, _ = server_with_state

        conn.request(
            "GET",
            "/diagram.svg",
            headers={"Cookie": "puml_session=wrong-value"},
        )
        response = conn.getresponse()
        response.read()

        assert response.status == 403

    def test_unknown_path_returns_404(
        self, server_with_state: tuple[HTTPConnection, DiagramState, str]
    ) -> None:
        conn, _, _ = server_with_state

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
