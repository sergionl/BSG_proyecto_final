"""Sirve mcp_server.py como app ASGI independiente, en modo stateless.

Correr con: uvicorn api.mcp:app --reload --port 8001
Disponible en http://127.0.0.1:8001/
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_server import mcp  # noqa: E402

# stateless_http=True: cada solicitud abre un contexto nuevo. Es el modo
# pensado para entornos sin garantia de "instancia fija" (ej. Vercel, cuando
# se intente ese paso opcional mas adelante).
app = mcp.http_app(path="/", stateless_http=True)
