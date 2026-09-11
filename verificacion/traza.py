"""Instrumentacion: convierte una corrida real del agente en una traza
estructurada (ToolCall de deepeval), tal como pide la Clase 7 ("de print a
medicion"). NO modifica mvp/agent.py: reutiliza sus funciones tal cual,
igual que ya hacian mvp/tests/test_security*.py.

sys.path apunta a mvp/ para importar el agente real (mismo patron que usan
los tests dentro de mvp/tests/).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

MVP_DIR = Path(__file__).resolve().parent.parent / "mvp"
sys.path.insert(0, str(MVP_DIR))

from deepeval.test_case import ToolCall  # noqa: E402

from agent import _build_agent  # noqa: E402  (reutilizado, no reimplementado)


@dataclass
class Traza:
    """Resultado de una corrida real del agente, listo para armar un
    LLMTestCase de deepeval."""

    texto: str
    tools_called: list[ToolCall] = field(default_factory=list)
    datos: Optional[dict[str, Any]] = None  # ultimo resultado de analizar_foto, ya parseado


def _parsear_contenido_tool(content: Any) -> Any:
    """El resultado de una tool MCP llega como str o como
    [{"type": "text", "text": "<json>"}]; lo normaliza a dict/valor python."""
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                try:
                    return json.loads(part["text"])
                except (json.JSONDecodeError, TypeError):
                    return part.get("text")
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


async def ejecutar_con_traza(mensaje: str) -> Traza:
    """Invoca al agente real (mismo camino que agent.responder()) y arma
    la traza estructurada: que tool llamo, con que argumentos, y que
    devolvio -- lo que ToolCorrectnessMetric y ArgumentCorrectnessMetric
    necesitan para medir, en vez de que un humano lea la traza impresa."""
    agent = await _build_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": mensaje}]})
    messages = result.get("messages", [])

    # 1. Indexar los resultados de tool por tool_call_id.
    resultados_por_id: dict[str, Any] = {}
    for message in messages:
        if type(message).__name__ == "ToolMessage":
            tool_call_id = getattr(message, "tool_call_id", None)
            if tool_call_id:
                resultados_por_id[tool_call_id] = _parsear_contenido_tool(message.content)

    # 2. Recorrer los AIMessage con tool_calls y emparejar con su resultado.
    tools_called: list[ToolCall] = []
    ultimo_dato: Optional[dict[str, Any]] = None
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            call_id = call.get("id")
            output = resultados_por_id.get(call_id)
            tools_called.append(
                ToolCall(
                    name=call.get("name", ""),
                    input_parameters=call.get("args", {}),
                    output=output,
                )
            )
            if isinstance(output, dict):
                ultimo_dato = output

    texto = messages[-1].content if messages else ""
    return Traza(texto=texto, tools_called=tools_called, datos=ultimo_dato)
