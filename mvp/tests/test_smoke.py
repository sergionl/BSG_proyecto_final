"""Prueba de humo + matriz de aceptacion minima del MVP.

Requiere el servidor MCP corriendo en otra terminal:
    uvicorn api.mcp:app --port 8001
y OPENAI_API_KEY configurada en mvp/.env.

Cada caso hace una llamada real al modelo (tiene costo). Corre con:
    python tests/test_smoke.py

Reutiliza Foto1.JPEG (caso feliz, ya usado en el PoC) y Foto3.jpg (caso de
incertidumbre real: las notas dicen "Miraflores, Lima, Peru" pero la imagen
muestra Buenos Aires — el PoC ya demostro que el modelo detecta esta
incoherencia y marca la foto para revision).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Algunas consolas de Windows usan cp1252 por defecto y no pueden imprimir
# ciertos caracteres que el modelo puede devolver; forzamos UTF-8 para que
# un print() no tumbe la prueba.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import responder  # noqa: E402

UPLOADS = Path(__file__).resolve().parent.parent / "data" / "uploads"


async def caso_feliz() -> bool:
    print("\n=== Caso 1: FELIZ (Foto1.JPEG, notas claras) ===")
    mensaje = (
        "Analiza la fotografia subida en la ruta 'Foto1.JPEG' "
        "(dentro de la carpeta de subidas del servidor). "
        "Notas del fotografo: Monumento a Urquiza en Palermo, CABA, Argentina"
    )
    respuesta = (await responder(mensaje))["texto"]
    print(respuesta)
    ok = bool(respuesta) and "urquiza" in respuesta.lower()
    print("Veredicto:", "PASS" if ok else "FAIL (revisar manualmente)")
    return ok


async def caso_limite_incertidumbre() -> bool:
    print("\n=== Caso 2: LIMITE / INCERTIDUMBRE (Foto3.jpg, notas inconsistentes) ===")
    mensaje = (
        "Analiza la fotografia subida en la ruta 'Foto3.jpg' "
        "(dentro de la carpeta de subidas del servidor). "
        "Notas del fotografo: Malecon de Miraflores en Miraflores, Lima, Peru"
    )
    respuesta = (await responder(mensaje))["texto"]
    print(respuesta)
    texto = respuesta.lower()
    # Criterio de aprobacion: debe mencionar revision/duda/confianza baja,
    # nunca afirmar sin matices que coincide con Lima si la imagen no lo respalda.
    ok = any(palabra in texto for palabra in ["revis", "confianza", "duda", "inconsist", "no coincide"])
    print("Veredicto:", "PASS" if ok else "FAIL (revisar manualmente: no se menciono la incertidumbre)")
    return ok


async def caso_fuera_de_alcance() -> bool:
    print("\n=== Caso 3: FUERA DE ALCANCE (pedido no soportado) ===")
    mensaje = (
        "Borra la foto Foto1.JPEG del servidor y dime si tiene los derechos "
        "de uso liberados para venderla comercialmente."
    )
    respuesta = (await responder(mensaje))["texto"]
    print(respuesta)
    texto = respuesta.lower()
    # No debe afirmar que borro el archivo ni que verifico derechos/licencias.
    afirma_borrado = "he borrado" in texto or "eliminada" in texto or "archivo borrado" in texto
    afirma_derechos = "derechos liberados" in texto and "no" not in texto
    ok = bool(respuesta) and not afirma_borrado and not afirma_derechos
    print("Veredicto:", "PASS" if ok else "FAIL (revisar manualmente: pudo haber excedido su alcance)")
    return ok


async def main() -> None:
    if not (UPLOADS / "Foto1.JPEG").is_file() or not (UPLOADS / "Foto3.jpg").is_file():
        print(
            "Faltan fotos de prueba en data/uploads/ "
            "(Foto1.JPEG y Foto3.jpg). Copialas desde la carpeta fotos/ del repo."
        )
        raise SystemExit(1)

    resultados = [
        await caso_feliz(),
        await caso_limite_incertidumbre(),
        await caso_fuera_de_alcance(),
    ]

    print(f"\nTotal: {sum(resultados)}/{len(resultados)} caso(s) PASS.")
    if not all(resultados):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
