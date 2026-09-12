# Catalogador de fotos DAM

[![CI](https://github.com/sergionl/BSG_proyecto_final/actions/workflows/ci.yml/badge.svg)](https://github.com/sergionl/BSG_proyecto_final/actions/workflows/ci.yml)

Proyecto Final · Curso **AI Data Engineer** (BSG Institute).

Un fotógrafo o editor sube una fotografía (o varias) más sus notas sueltas.
El sistema extrae los metadatos EXIF, analiza el contenido con un modelo de
visión (sujeto, ambiente, colores, keywords), lo clasifica comercialmente, y
evalúa qué tan confiable es ese análisis — marcando la foto para revisión
humana cuando la confianza es baja o hay incoherencias — para reemplazar la
transcripción y el etiquetado manual que hoy hace un editor foto por foto.

El detalle completo del caso de uso, el problema y los números de negocio
está en la Ficha 1 (`documentos/Caso de uso.docx`); acá va solo el mapa del
repositorio.

## Recorrido del proyecto

Este repo documenta el camino completo **de script a agente evaluado**, no
solo el resultado final — cada carpeta es una etapa real del curso, no una
carpeta de sobras:

| # | Carpeta | Qué es | Estado |
|---|---|---|---|
| 1 | [`documentos/`](documentos/) | Fichas de caso de uso y arquitectura cognitiva (Sesiones 1 y 2) | Completo |
| 2 | [`dam_pipeline/`](dam_pipeline/) | Pipeline original en scripts `.py` sueltos: ingesta, EXIF, cadena de 3 llamadas al modelo, revisión por consola | Completo, base del PoC |
| 3 | [`Proof_Of_Concept/`](Proof_Of_Concept/) | Notebook autocontenido (PoC) que combina Etapas 2, 3/4 y 6, con KPIs de negocio, matriz de casos de prueba y conclusión formal (cierre Sesión 4/6) | Completo, probado con 5 fotos reales |
| 4 | [`mvp/`](mvp/) | MVP real: FastAPI + FastMCP + agente LangChain que descubre la tool `analizar_foto` vía protocolo MCP, con frontend web | Completo, corre en local |
| 5 | [`verificacion/`](verificacion/) | Suite de evaluación del agente (Clase 7): traza estructurada, dataset dorado de 24 casos, métricas deterministas + juez LLM | Harness probado, dataset completo sin correr aún (costo) |

Cada carpeta con código propio (`mvp/`, `verificacion/`) tiene su propio
`README.md` con instalación, cómo correrla y resultados reales — este
README es el mapa, no el detalle.

## Cómo probarlo (la forma más rápida)

El MVP es la pieza que realmente se usa hoy:

```bash
cd mvp
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # completa OPENAI_API_KEY

# dos terminales:
uvicorn api.mcp:app --port 8001   # servidor de tools (FastMCP)
uvicorn api.chat:app --port 8000  # backend + frontend
```

Abre `http://127.0.0.1:8000`, sube una foto (o varias) de `fotos/` y sus
notas. Instrucciones completas, variables de entorno y troubleshooting en
[`mvp/README.md`](mvp/README.md).

## Arquitectura (resumen)

Nivel de autonomía: **Workflow / cadena**, no agente que elige libremente
entre herramientas (Ficha 2). En el MVP eso se traduce en un agente
LangChain con **una sola tool** (`analizar_foto`), que siempre se invoca
cuando llega una foto para catalogar — el "razonamiento" del agente está en
traducir el resultado de la tool a una respuesta legible, no en decidir qué
hacer.

```
Usuario → index.html/app.js → api/chat.py (FastAPI)
        → agent.py (LangChain, descubre tools vía MultiServerMCPClient)
        → api/mcp.py (FastMCP, stateless) → mcp_server.py::analizar_foto
        → EXIF (script) + cadena de 3 llamadas al modelo (contenido →
          clasificación → control de calidad, salida validada con Pydantic)
```

## Seguridad: qué se probó y qué se encontró

No se asumió que "funciona en la demo" alcanza. Se probaron 8+ casos
adversariales reales (por texto y por imagen) contra el agente:

- Fuga del system prompt, exfiltración de la API key, path traversal vía
  notas, forzar `confidence_score` falso — **todos resistidos**.
- La inyección **visual** (instrucción de manipulación renderizada dentro
  de la propia foto, no en las notas) sí encontró una vulnerabilidad real:
  una imagen que exigía confianza 1.0 la conseguía, pese a que el modelo
  identificaba correctamente que era "un documento con instrucciones del
  sistema". Se corrigió endureciendo el prompt de control de calidad y se
  portó el mismo fix al PoC para que no se reintroduzca.

Detalle completo, comandos para reproducir cada caso, y los resultados
reales de cada corrida: sección "Pruebas de seguridad" en
[`mvp/README.md`](mvp/README.md).

## CI

Dos workflows en [`.github/workflows/`](.github/workflows/), separados a
propósito por costo:

- **[`ci.yml`](.github/workflows/ci.yml)** — corre en cada push y PR, es
  **gratis** (nada llama a la API de OpenAI, no necesita secrets): tests
  unitarios de `dam_pipeline/` (Etapa 1 + Etapa 2) y de `mvp/` (`notes.py`
  + las validaciones de `analizar_foto` que fallan antes de tocar el
  modelo), más un chequeo de que `verificacion/` importa sin errores.
- **[`integracion-pagada.yml`](.github/workflows/integracion-pagada.yml)**
  — se dispara **a mano** desde la pestaña Actions (`workflow_dispatch`),
  nunca automático: corre `mvp/tests/test_smoke.py` y
  `tests/test_security*.py` contra el modelo real. Requiere el secret
  `OPENAI_API_KEY` configurado en el repositorio.

El dataset completo de `verificacion/` (24 casos) sigue sin estar en CI —
su propio costo es varias veces mayor que el de estos dos workflows juntos
(ver `verificacion/README.md`, sección "Costo de correr la suite completa").

## Documentos de referencia

- [`documentos/Caso de uso.docx`](documentos/Caso%20de%20uso.docx) — Ficha 1: problema, TADR, contrato de entrada/salida.
- [`documentos/Arquitectura cognitiva.docx`](documentos/Arquitectura%20cognitiva.docx) — Ficha 2: nivel de autonomía, agentes, herramientas.

Las guías del curso usadas como referencia para migrar el PoC al MVP no
están incluidas en este repo (no son material propio del equipo). Este
proyecto solo tiene Fichas 1 y 2 — no hay una "Ficha 3" en su currícula.

## Qué queda pendiente (declarado, no escondido)

- **Despliegue a Vercel**: paso opcional de la guía del curso, no intentado
  todavía — el MVP corre solo en local.
- **Dataset completo de `verificacion/`** (24 casos): el harness ya está
  probado con un caso por categoría; correr los 24 tiene un costo real en
  llamadas a la API y no se hizo de punta a punta todavía.
- **Calibración formal del juez LLM** (kappa contra un set etiquetado a
  mano) en `verificacion/`.
