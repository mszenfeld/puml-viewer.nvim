"""Tests for DiagramState management."""

from __future__ import annotations

from server.server import DiagramState


class TestDiagramState:
    """Test diagram state storage and retrieval."""

    def test_initial_state_returns_empty_svg(self) -> None:
        state = DiagramState()

        response = state.get_response()

        assert response == '<svg xmlns="http://www.w3.org/2000/svg"/>'

    def test_set_svg_stores_content(self) -> None:
        state = DiagramState()

        state.set_svg("<svg><text>test</text></svg>")

        assert state.svg_content == "<svg><text>test</text></svg>"
        assert state.error is None

    def test_set_error_stores_error_message(self) -> None:
        state = DiagramState()

        state.set_error("Syntax error on line 5")

        assert state.error == "Syntax error on line 5"
        assert state.svg_content is None

    def test_get_response_returns_svg_when_available(self) -> None:
        state = DiagramState()
        state.set_svg("<svg><circle/></svg>")

        response = state.get_response()

        assert response == "<svg><circle/></svg>"

    def test_get_response_returns_error_prefixed(self) -> None:
        state = DiagramState()
        state.set_error("Invalid diagram")

        response = state.get_response()

        assert response.startswith("ERROR:")
        assert "Invalid diagram" in response

    def test_set_svg_clears_previous_error(self) -> None:
        state = DiagramState()
        state.set_error("some error")

        state.set_svg("<svg/>")

        assert state.error is None
        assert state.svg_content == "<svg/>"

    def test_set_error_clears_previous_svg(self) -> None:
        state = DiagramState()
        state.set_svg("<svg/>")

        state.set_error("new error")

        assert state.svg_content is None
        assert state.error == "new error"
