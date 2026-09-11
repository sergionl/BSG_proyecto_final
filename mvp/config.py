"""Configuracion del MVP: variables de entorno, nunca secretos en codigo.

Decision heredada del PoC (ver dam_pipeline/llm_client.py): se usa la API
directa de OpenAI, no OpenRouter. La guia del curso lo permite explicitamente
("el proveedor que el equipo haya elegido").
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL_ID = os.environ.get("MODEL_ID", "gpt-5.6-luna")
MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8001/")
CONFIDENCE_REVIEW_THRESHOLD = float(os.environ.get("CONFIDENCE_REVIEW_THRESHOLD", "0.80"))

LANGSMITH_TRACING = os.environ.get("LANGSMITH_TRACING", "")
if LANGSMITH_TRACING:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ.get("LANGSMITH_API_KEY", ""))
    os.environ.setdefault("LANGCHAIN_PROJECT", os.environ.get("LANGSMITH_PROJECT", "dam-mvp"))
