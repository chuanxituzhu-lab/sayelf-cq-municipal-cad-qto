from __future__ import annotations

import json
import os
import secrets
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from mcp_server import handle_request


class McpHttpHandler(BaseHTTPRequestHandler):
    server_version = "MunicipalCadQtoMcp/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print(fmt % args, file=sys.stderr)

    def _authorized(self) -> bool:
        expected = os.environ.get("MUNICIPAL_QTO_HTTP_TOKEN", "").strip()
        if not expected:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {expected}"

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK, session_id: str = "") -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if session_id:
            self.send_header("Mcp-Session-Id", session_id)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/healthz":
            self._send_json({"ok": True, "service": "municipal-cad-qto", "transport": "streamable-http"})
            return
        self._send_json({"error": "仅支持 /mcp POST 和 /healthz GET"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/mcp":
            self._send_json({"error": "仅支持 /mcp POST"}, HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json({"error": "MCP 鉴权失败"}, HTTPStatus.UNAUTHORIZED)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"error": "Content-Length 不合法"}, HTTPStatus.BAD_REQUEST)
            return
        if length <= 0 or length > 8 * 1024 * 1024:
            self._send_json({"error": "请求体为空或过大"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("MCP 请求必须是 JSON 对象")
            response = handle_request(request)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if response is None:
            self.send_response(HTTPStatus.ACCEPTED)
            self.end_headers()
            return
        session_id = self.headers.get("Mcp-Session-Id", "")
        if request.get("method") == "initialize":
            session_id = secrets.token_urlsafe(18)
            self.server.mcp_sessions.add(session_id)
        elif session_id and session_id not in self.server.mcp_sessions:
            self._send_json({"error": "MCP 会话不存在或已失效"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json(response, session_id=session_id)

    def do_DELETE(self) -> None:
        if urlparse(self.path).path != "/mcp":
            self._send_json({"error": "仅支持 /mcp DELETE"}, HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json({"error": "MCP 鉴权失败"}, HTTPStatus.UNAUTHORIZED)
            return
        session_id = self.headers.get("Mcp-Session-Id", "")
        if session_id:
            self.server.mcp_sessions.discard(session_id)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()


def create_server() -> ThreadingHTTPServer:
    host = os.environ.get("MUNICIPAL_QTO_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("MUNICIPAL_QTO_HTTP_PORT", "8787"))
    token = os.environ.get("MUNICIPAL_QTO_HTTP_TOKEN", "").strip()
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise RuntimeError("非本机绑定必须设置 MUNICIPAL_QTO_HTTP_TOKEN")
    server = ThreadingHTTPServer((host, port), McpHttpHandler)
    server.mcp_sessions = set()
    return server


def main() -> int:
    server = create_server()
    print(f"municipal-cad-qto MCP HTTP listening on {server.server_address[0]}:{server.server_address[1]}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
