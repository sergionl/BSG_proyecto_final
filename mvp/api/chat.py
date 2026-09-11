"""FastAPI: sirve index.html, /static, y expone POST /api/analizar.

No contiene logica del agente ni de la tool: solo recibe el formulario
(una o varias fotos + notas escritas o en archivo), guarda las imagenes en
data/uploads/ y llama a agent.responder() una vez por foto.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import sys
import uuid
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from agent import responder
from notes import NotesExtractionError, extract_notes_text, match_notes_to_photos

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mvp.api.chat")

ROOT = Path(__file__).resolve().parent.parent

app = FastAPI(title="Catalogador de fotos DAM - MVP")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

_ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB por foto
_MAX_FOTOS_POR_LOTE = 20


def _to_data_url(data: bytes, filename: str) -> str:
    """Codifica la imagen para mostrarla en el navegador sin exponer una
    ruta publica nueva (nada de montar data/uploads/ como estatico)."""
    mime = mimetypes.guess_type(filename)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.post("/api/analizar")
async def analizar(
    imagenes: List[UploadFile] = File(...),
    notas_texto: str = Form(""),
    notas_archivo: Optional[UploadFile] = File(None),
):
    if not imagenes:
        return JSONResponse(status_code=400, content={"error": "Sube al menos una fotografia."})
    if len(imagenes) > _MAX_FOTOS_POR_LOTE:
        return JSONResponse(
            status_code=400,
            content={"error": f"Maximo {_MAX_FOTOS_POR_LOTE} fotos por lote."},
        )

    # --- 1. Resolver el texto de notas: archivo tiene prioridad sobre lo escrito ---
    notas_raw = notas_texto.strip()
    if notas_archivo is not None and notas_archivo.filename:
        contenido_notas = await notas_archivo.read()
        try:
            notas_raw = extract_notes_text(notas_archivo.filename, contenido_notas)
        except NotesExtractionError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

    # --- 2. Validar y guardar cada foto, conservando su nombre original ---
    originales: List[str] = []
    guardadas: dict[str, str] = {}  # nombre original -> nombre guardado en disco
    contenidos: dict[str, bytes] = {}  # nombre original -> bytes (para el preview)

    for imagen in imagenes:
        suffix = Path(imagen.filename or "").suffix.lower()
        if suffix not in _ALLOWED_IMAGE_SUFFIXES:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Formato no soportado en '{imagen.filename}': '{suffix}'. "
                    "Usa jpg, jpeg, png o webp."
                },
            )

        contents = await imagen.read()
        if len(contents) > _MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=400,
                content={"error": f"'{imagen.filename}' supera el tamano maximo (15 MB)."},
            )
        if not contents:
            return JSONResponse(
                status_code=400, content={"error": f"'{imagen.filename}' esta vacio."}
            )

        nombre_original = imagen.filename or f"foto_{len(originales) + 1}{suffix}"
        saved_name = f"{uuid.uuid4().hex[:10]}{suffix}"
        (config.UPLOADS_DIR / saved_name).write_bytes(contents)

        originales.append(nombre_original)
        guardadas[nombre_original] = saved_name
        contenidos[nombre_original] = contents

    # --- 3. Emparejar las notas con cada foto (igual que la Etapa 1 del PoC) ---
    notas_por_foto = match_notes_to_photos(notas_raw, originales)

    # --- 4. Analizar cada foto por separado; una que falle no aborta el lote ---
    resultados = []
    for nombre_original in originales:
        saved_name = guardadas[nombre_original]
        notas_foto = notas_por_foto.get(nombre_original, "")
        mensaje = (
            f"Analiza la fotografia subida en la ruta '{saved_name}' "
            "(dentro de la carpeta de subidas del servidor). "
            f"Notas del fotografo: {notas_foto or '(sin notas)'}"
        )
        imagen_data_url = _to_data_url(contenidos[nombre_original], nombre_original)
        try:
            resultado_agente = await responder(mensaje)
            resultados.append(
                {
                    "archivo": nombre_original,
                    "texto": resultado_agente["texto"],
                    "datos": resultado_agente["datos"],
                    "imagen_data_url": imagen_data_url,
                }
            )
        except Exception as exc:
            logger.error("Fallo al analizar %s: %s", nombre_original, exc)
            resultados.append(
                {
                    "archivo": nombre_original,
                    "error": (
                        "No se pudo completar el analisis de esta foto. Verifica que el "
                        "servidor MCP (uvicorn api.mcp:app --port 8001) este corriendo y "
                        "que OPENAI_API_KEY este configurada en .env."
                    ),
                    "imagen_data_url": imagen_data_url,
                }
            )

    return {"resultados": resultados}
