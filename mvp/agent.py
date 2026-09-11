"""Agente LangChain que descubre la tool `analizar_foto` via MCP.

Importante: este modulo NUNCA importa mcp_server.analizar_foto directamente.
El agente descubre la tool por protocolo (MultiServerMCPClient -> get_tools),
igual que lo haria un cliente MCP externo, para poder reutilizar el servidor
de tools desde otro agente o interfaz sin acoplarse a la implementacion.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

import config
from prompts import SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mvp.agent")

_agent = None


def _get_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "catalogador": {
                "transport": "streamable_http",
                "url": config.MCP_URL,
            }
        }
    )


async def _build_agent():
    global _agent
    if _agent is not None:
        return _agent

    if not config.OPENAI_API_KEY:
        raise RuntimeError(
            "Falta OPENAI_API_KEY. Copia .env.example a .env en mvp/ y completa la clave."
        )

    client = _get_mcp_client()
    tools = await client.get_tools()
    if not tools:
        raise RuntimeError(
            f"No se descubrio ninguna tool en {config.MCP_URL}. "
            "Verifica que api/mcp.py este corriendo (uvicorn api.mcp:app --port 8001)."
        )
    logger.info("Tools descubiertas via MCP: %s", [t.name for t in tools])

    # gpt-5.6-luna aplica reasoning_effort por defecto en el servidor, lo que
    # choca con function tools en /v1/chat/completions (error 400 de OpenAI).
    # El propio mensaje de error indica el fix: forzar reasoning_effort="none".
    model = ChatOpenAI(
        model=config.MODEL_ID,
        api_key=config.OPENAI_API_KEY,
        reasoning_effort="none",
    )
    _agent = create_agent(model, tools, system_prompt=SYSTEM_PROMPT)
    return _agent


def _extraer_datos_tool(messages: list) -> Optional[dict[str, Any]]:
    """Busca el ultimo ToolMessage (resultado real de analizar_foto) y lo
    parsea. Es el dato estructurado (AnalisisFoto) que el frontend usa para
    renderizar el resultado; el texto del agente es solo un resumen."""
    for message in reversed(messages):
        if type(message).__name__ != "ToolMessage":
            continue
        content = message.content
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    try:
                        return json.loads(part["text"])
                    except (json.JSONDecodeError, TypeError):
                        continue
        elif isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                continue
    return None


async def responder(mensaje: str) -> dict[str, Any]:
    """Invoca al agente con `mensaje` y devuelve tanto el texto final como
    el resultado estructurado de la tool (para que el frontend lo renderice
    de forma deterministica, sin depender de como el modelo redacto el
    resumen).

    `mensaje` debe incluir la ruta de la imagen ya subida (dentro de
    data/uploads/) y, opcionalmente, las notas del fotografo — ver
    api/chat.py, que arma este mensaje a partir del formulario.
    """
    agent = await _build_agent()
    try:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": mensaje}]})
    except Exception as exc:  # servidor MCP caido, error del modelo, etc.
        logger.error("Fallo al invocar el agente: %s", exc)
        raise

    messages = result.get("messages", [])
    texto = messages[-1].content if messages else "El agente no genero una respuesta."
    datos = _extraer_datos_tool(messages)
    return {"texto": texto, "datos": datos}
