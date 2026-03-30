"""Tests for WebSocket handshake and frame handling."""

from __future__ import annotations

import io
import struct

import pytest

from server.server import WebSocketClient, ws_accept_key


class TestWsAcceptKey:
    """Test RFC 6455 WebSocket accept key computation."""

    def test_computes_correct_accept_key_for_known_vector(self) -> None:
        # RFC 6455 Section 4.2.2 example
        client_key = "dGhlIHNhbXBsZSBub25jZQ=="
        expected = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="

        result = ws_accept_key(client_key)

        assert result == expected

    def test_returns_different_keys_for_different_inputs(self) -> None:
        key_a = ws_accept_key("AAAAAAAAAAAAaaaa")
        key_b = ws_accept_key("BBBBBBBBBBBBbbbb")

        assert key_a != key_b

    def test_returns_base64_encoded_string(self) -> None:
        result = ws_accept_key("dGhlIHNhbXBsZSBub25jZQ==")

        assert result.endswith("=")
        assert isinstance(result, str)


class TestWebSocketClientSendText:
    """Test WebSocket text frame building."""

    @pytest.fixture()
    def ws_client(self) -> WebSocketClient:
        rfile = io.BytesIO()
        wfile = io.BytesIO()
        return WebSocketClient(rfile=rfile, wfile=wfile)

    def test_sends_small_text_frame(self, ws_client: WebSocketClient) -> None:
        ws_client.send_text("reload")

        ws_client.wfile.seek(0)
        data = ws_client.wfile.read()

        # First byte: FIN=1, opcode=1 (text) → 0x81
        assert data[0] == 0x81
        # Second byte: payload length (no mask for server→client)
        assert data[1] == len(b"reload")
        # Payload
        assert data[2:] == b"reload"

    def test_sends_medium_text_frame(self, ws_client: WebSocketClient) -> None:
        payload = "x" * 200

        ws_client.send_text(payload)

        ws_client.wfile.seek(0)
        data = ws_client.wfile.read()

        assert data[0] == 0x81
        # Length marker for 126-65535 range
        assert data[1] == 126
        encoded_length = struct.unpack("!H", data[2:4])[0]
        assert encoded_length == 200
        assert data[4:] == payload.encode("utf-8")

    def test_marks_client_closed_on_write_error(
        self, ws_client: WebSocketClient
    ) -> None:
        ws_client.wfile.close()

        ws_client.send_text("test")

        assert ws_client.closed is True


class TestWebSocketClientReadFrame:
    """Test WebSocket frame parsing."""

    def _build_masked_text_frame(self, text: str) -> bytes:
        """Build a masked text frame as a browser would send."""
        payload = text.encode("utf-8")
        mask_key = b"\x01\x02\x03\x04"
        masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        frame = bytearray()
        frame.append(0x81)  # FIN + text opcode
        frame.append(0x80 | len(payload))  # masked + length
        frame.extend(mask_key)
        frame.extend(masked_payload)
        return bytes(frame)

    def test_reads_masked_text_frame(self) -> None:
        frame_data = self._build_masked_text_frame("hello")
        rfile = io.BytesIO(frame_data)
        wfile = io.BytesIO()
        client = WebSocketClient(rfile=rfile, wfile=wfile)

        result = client.read_frame()

        assert result == "hello"

    def test_returns_none_for_close_frame(self) -> None:
        # Close frame: FIN + opcode 8, masked, zero-length
        frame = bytes([0x88, 0x80, 0x00, 0x00, 0x00, 0x00])
        rfile = io.BytesIO(frame)
        wfile = io.BytesIO()
        client = WebSocketClient(rfile=rfile, wfile=wfile)

        result = client.read_frame()

        assert result is None

    def test_returns_none_on_empty_stream(self) -> None:
        rfile = io.BytesIO(b"")
        wfile = io.BytesIO()
        client = WebSocketClient(rfile=rfile, wfile=wfile)

        result = client.read_frame()

        assert result is None
