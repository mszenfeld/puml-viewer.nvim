"""Tests for PlantUML rendering via subprocess."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from server.server import render_plantuml

SAMPLE_PUML = """@startuml
Alice -> Bob: Hello
@enduml"""

SAMPLE_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><text>diagram</text></svg>'


class TestRenderPlantuml:
    """Test PlantUML rendering with mocked subprocess (external I/O)."""

    @patch("server.server.subprocess.run")
    def test_returns_svg_on_success(self, mock_run: MagicMock) -> None:
        def fake_plantuml_run(cmd: list[str], **kwargs: object) -> MagicMock:
            # Find the input .puml file from the command args
            puml_file = Path(cmd[-1])
            svg_file = puml_file.with_suffix(".svg")
            svg_file.write_text(SAMPLE_SVG)
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_plantuml_run

        svg, error = render_plantuml(SAMPLE_PUML, "plantuml")

        assert svg == SAMPLE_SVG
        assert error is None

    @patch("server.server.subprocess.run")
    def test_returns_error_on_nonzero_exit(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1, stderr="Syntax Error line 2"
        )

        svg, error = render_plantuml(SAMPLE_PUML, "plantuml")

        assert svg is None
        assert error is not None
        assert "Syntax Error" in error

    @patch("server.server.subprocess.run")
    def test_returns_error_on_timeout(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="plantuml", timeout=10)

        svg, error = render_plantuml(SAMPLE_PUML, "plantuml")

        assert svg is None
        assert error is not None
        assert "timed out" in error.lower()

    @patch("server.server.subprocess.run")
    def test_returns_error_when_command_not_found(
        self, mock_run: MagicMock
    ) -> None:
        mock_run.side_effect = FileNotFoundError()

        svg, error = render_plantuml(SAMPLE_PUML, "nonexistent_cmd")

        assert svg is None
        assert error is not None
        assert "not found" in error.lower()

    def test_returns_error_when_empty_content(self) -> None:
        svg, error = render_plantuml("", "plantuml")

        assert svg is None
        assert error is not None

    @patch("server.server.subprocess.run")
    def test_splits_plantuml_cmd_with_spaces(
        self, mock_run: MagicMock
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="test")

        render_plantuml(SAMPLE_PUML, "java -jar plantuml.jar")

        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "java"
        assert called_cmd[1] == "-jar"
        assert called_cmd[2] == "plantuml.jar"

    @patch("server.server.subprocess.run")
    def test_cleans_up_temp_file_on_success(self, mock_run: MagicMock) -> None:
        created_files: list[Path] = []

        def fake_plantuml_run(cmd: list[str], **kwargs: object) -> MagicMock:
            puml_file = Path(cmd[-1])
            created_files.append(puml_file)
            svg_file = puml_file.with_suffix(".svg")
            svg_file.write_text(SAMPLE_SVG)
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_plantuml_run

        render_plantuml(SAMPLE_PUML, "plantuml")

        # Temp .puml file should be cleaned up
        assert len(created_files) == 1
        assert not created_files[0].exists()
