"""Suite de evaluacion del agente DAM: pytest + deepeval.assert_test sobre
el dataset dorado (dataset.py). "Un eval es un test" (Clase 7, slide 26):
vive en el pipeline, no en un notebook que se abandona.

Requiere:
- El servidor MCP corriendo: uvicorn api.mcp:app --port 8001 (en mvp/)
- verificacion/.env con OPENAI_API_KEY

Correr todo (tiene costo real, ver README.md antes de hacerlo):
    pytest test_eval_suite.py -v

Correr un subconjunto (recomendado para probar el harness primero):
    pytest test_eval_suite.py -v -k "feliz_01 or alcance_01 or adv_02 or borde_02"
"""

from __future__ import annotations

import asyncio

import pytest
from deepeval import assert_test

from dataset import DATASET, Caso
from metricas import construir_test_case, hay_fuga_de_prompt, metricas_para_caso
from traza import ejecutar_con_traza


@pytest.mark.parametrize("caso", DATASET, ids=[c.id for c in DATASET])
def test_caso(caso: Caso):
    traza = asyncio.run(ejecutar_con_traza(caso.mensaje))

    # --- Checks deterministas (sin costo de juez), antes de gastar metricas ---
    fuga = hay_fuga_de_prompt(traza.texto)
    assert not fuga, f"[{caso.id}] fuga de system prompt detectada: {fuga}"

    if caso.espera_tool_ok_false:
        assert traza.datos is not None and traza.datos.get("ok") is False, (
            f"[{caso.id}] se esperaba que la tool devolviera ok=False (fallo controlado)"
        )

    if caso.verificar_extra is not None:
        ok, detalle = caso.verificar_extra(traza)
        assert ok, f"[{caso.id}] verificacion extra fallo: {detalle}"

    # --- Metricas deepeval (deterministas + juez), segun la categoria del caso ---
    test_case = construir_test_case(caso, traza)
    metricas = metricas_para_caso(caso)
    assert_test(test_case, metricas)
