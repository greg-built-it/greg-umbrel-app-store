#!/usr/bin/env python3
"""
MCP-Server fuer die Umbrel Read-Only Bridge.

Liest das Token ausschliesslich aus /run/secrets/bridge-token.
Kein Env-Fallback; das Token darf nicht im Container-Image, in Logs,
docker inspect oder der Service-Umgebung erscheinen.
"""

import asyncio
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent, Tool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
import uvicorn

from umbrel_ro_bridge import fs
from umbrel_ro_bridge.secrets_filter import mask_secrets


# ---------------------------------------------------------------------------
# Token laden (nur aus Secret-Datei)
# ---------------------------------------------------------------------------

TOKEN_FILE = Path("/run/secrets/bridge-token")


def _load_token() -> str:
    try:
        return TOKEN_FILE.read_text().strip()
    except OSError as e:
        raise RuntimeError(f"Token-Datei nicht lesbar: {e}")


# Lazy initialisierung: das Token wird erst beim Server-Start gelesen,
# damit der Modul-Import auch ohne Secret-Datei funktioniert.
BRIDGE_TOKEN: str | None = None


# ---------------------------------------------------------------------------
# MCP-Server
# ---------------------------------------------------------------------------

app = Server("umbrel-ro-bridge")


def _token_path_guard(path: str) -> None:
    lowered = path.lower()
    if "/run/secrets/bridge-token" in lowered or ".bridge-token" in lowered or "bridge-token" in lowered:
        raise fs.FilesystemError("Zugriff auf Token-Quelle verweigert.")


TOOLS = [
    Tool(name="list_directory", description="Listet Eintraege eines erlaubten Verzeichnisses auf.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    Tool(name="read_text", description="Liest eine Textdatei (max. 5 MiB).", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer", "maximum": 5242880}}, "required": ["path"]}),
    Tool(name="read_binary_metadata", description="Liest Metadaten und MIME-Typ einer Datei.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    Tool(name="read_binary_chunk", description="Liest ein begrenztes Byte-Chunks aus einer Datei (max. 64 KiB).", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}, "length": {"type": "integer", "minimum": 1, "maximum": 65536}}, "required": ["path", "offset", "length"]}),
    Tool(name="archive_list", description="Listet den Inhalt eines ZIP/TAR-Archivs auf.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "max_entries": {"type": "integer", "maximum": 1000}}, "required": ["path"]}),
    Tool(name="sqlite_query", description="Fuehrt eine read-only SQLite-Abfrage aus.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "query": {"type": "string"}, "max_rows": {"type": "integer", "maximum": 1000}}, "required": ["path", "query"]}),
    Tool(name="extract_pdf_text", description="Extrahiert Text aus einer PDF-Datei (max. 50 Seiten).", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "max_pages": {"type": "integer", "maximum": 50}}, "required": ["path"]}),
    Tool(name="sha256", description="Berechnet SHA-256 einer Datei.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    Tool(name="find_files", description="Sucht Dateien unter einem Verzeichnis.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "name": {"type": "string"}, "size": {"type": "string"}, "mtime_days": {"type": "integer"}, "maxdepth": {"type": "integer", "maximum": 5}}, "required": ["path"]}),
    Tool(name="grep_text", description="Sucht in einer Textdatei.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "pattern": {"type": "string"}, "max_matches": {"type": "integer", "maximum": 1000}}, "required": ["path", "pattern"]}),
    Tool(name="mount_inventory", description="Listet Mounts unter /host/umbrel auf.", inputSchema={"type": "object", "properties": {}}),
    Tool(name="du", description="Ermittelt Groessen von Verzeichnissen.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}, "maxdepth": {"type": "integer", "maximum": 5}}, "required": ["path"]}),
    Tool(name="file_type", description="Gibt Dateityp/Statistik zurueck.", inputSchema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list:
    path = arguments.get("path", "")
    _token_path_guard(path)
    try:
        if name == "list_directory":
            result = fs.list_directory(path)
        elif name == "read_text":
            result = fs.read_text(path, limit=arguments.get("limit", fs.MAX_TEXT_BYTES))
        elif name == "read_binary_metadata":
            result = fs.read_binary_metadata(path)
        elif name == "read_binary_chunk":
            result = fs.read_binary_chunk(path, arguments.get("offset", 0), arguments.get("length", 4096))
        elif name == "archive_list":
            result = fs.archive_list(path, max_entries=arguments.get("max_entries", fs.MAX_ARCHIVE_ENTRIES))
        elif name == "sqlite_query":
            result = fs.sqlite_query(path, arguments["query"], max_rows=arguments.get("max_rows", fs.MAX_SQLITE_ROWS))
        elif name == "extract_pdf_text":
            result = fs.extract_pdf_text(path, max_pages=arguments.get("max_pages", 10))
        elif name == "sha256":
            result = fs.sha256(path)
        elif name == "find_files":
            result = fs.find_files(path, name=arguments.get("name"), size=arguments.get("size"), mtime_days=arguments.get("mtime_days"), maxdepth=arguments.get("maxdepth", 3))
        elif name == "grep_text":
            result = fs.grep_text(path, arguments["pattern"], max_matches=arguments.get("max_matches", fs.MAX_GREP_MATCHES))
        elif name == "mount_inventory":
            result = fs.mount_inventory()
        elif name == "du":
            result = fs.du(path, maxdepth=arguments.get("maxdepth", 2))
        elif name == "file_type":
            result = fs.file_type(path)
        else:
            raise ValueError(f"Unbekanntes Werkzeug: {name}")
        text = json.dumps(result, ensure_ascii=False, default=str)
        text = mask_secrets(text)
        return [TextContent(type="text", text=text)]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


@app.list_tools()
async def list_tools() -> list:
    return TOOLS


# ---------------------------------------------------------------------------
# HTTP/SSE-Transport mit Bearer-Token (secrets.compare_digest)
# ---------------------------------------------------------------------------


class AuthenticatedSseTransport(SseServerTransport):
    """SseServerTransport mit Bearer-Token-Pruefung."""

    def __init__(self, token: str, endpoint: str):
        super().__init__(endpoint)
        self._token = token

    @staticmethod
    def _auth_error(message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=401)

    async def connect_sse(self, request: Request):
        auth = request.headers.get("authorization", "")
        if not auth:
            return self._auth_error("Missing Authorization header")
        parts = auth.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return self._auth_error("Invalid Authorization scheme")
        provided = parts[1]
        if not provided or not secrets.compare_digest(provided, self._token):
            return self._auth_error("Invalid token")
        return await super().connect_sse(request)


def build_starlette_app(token: str | None = None):
    """Erzeugt die Starlette-App. Lädt das Token lazy, falls nicht übergeben."""
    if token is None:
        token = _load_token()

    sse = AuthenticatedSseTransport(token, "/messages/")

    async def _handle_sse(request: Request):
        return await sse.connect_sse(request)

    async def _handle_messages(request: Request):
        return await sse.handle_post_message(request)

    return Starlette(
        debug=False,
        routes=[
            Route("/sse", _handle_sse, methods=["GET"]),
            Route("/messages/", _handle_messages, methods=["POST"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
    )


starlette_app = None  # Wird lazy in main_http() erzeugt, damit der Import
                      # ohne /run/secrets/bridge-token funktioniert.


async def handle_health(request: Request):
    """Anonymer Health-Check ohne sensitive Daten."""
    return PlainTextResponse("ok", status_code=200)


async def main_http():
    global starlette_app
    if starlette_app is None:
        starlette_app = build_starlette_app()
    host = os.environ.get("BRIDGE_HOST", "0.0.0.0")
    port = int(os.environ.get("BRIDGE_PORT", "8080"))
    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


def main():
    asyncio.run(main_http())


if __name__ == "__main__":
    main()
