"""Cliente del modelo para la Etapa 3.

Usa la API directa de OpenAI (SDK `openai`) con el modelo GPT-5.6 Luna.
No pasa por OpenRouter: esto es una decision explicita para la Etapa 3,
distinta del notebook de Sesion 4 (que usa OpenRouter + Nemotron para el
PoC del agente). Si mas adelante el equipo quiere unificar proveedor,
solo hay que reemplazar `get_client()` y `MODEL_ID`.
"""

from __future__ import annotations

import base64
import getpass
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

MODEL_ID = "gpt-5.6-luna"
MAX_RETRIES = 2

# Formatos que se pueden mandar tal cual a un modelo de vision.
_DIRECT_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
# Formatos RAW de camara: no son un formato de imagen web, hay que
# revelarlos a JPEG antes de poder mandarlos al modelo.
_RAW_IMAGE_TYPES = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"}


class LLMCallError(RuntimeError):
    """El modelo no devolvio una respuesta usable tras los reintentos."""


def _get_api_key() -> str:
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = getpass.getpass("OPENAI_API_KEY: ")
    return os.environ["OPENAI_API_KEY"]


_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=_get_api_key())
    return _client


def _raw_to_jpeg_bytes(path: Path) -> bytes:
    try:
        import rawpy  # type: ignore
    except ImportError as exc:
        raise LLMCallError(
            f"'{path.name}' es un archivo RAW y se necesita el paquete "
            "'rawpy' (pip install rawpy) para revelarlo a JPEG antes de "
            "mandarlo al modelo."
        ) from exc

    import io
    from PIL import Image

    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess()

    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _image_to_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower()

    if suffix in _DIRECT_IMAGE_TYPES:
        mime = _DIRECT_IMAGE_TYPES[suffix]
        raw_bytes = image_path.read_bytes()
    elif suffix in _RAW_IMAGE_TYPES:
        mime = "image/jpeg"
        raw_bytes = _raw_to_jpeg_bytes(image_path)
    else:
        mime = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
        raw_bytes = image_path.read_bytes()
        logger.warning("Tipo de imagen no reconocido para %s; se envia como %s.", image_path, mime)

    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def call_json(system_prompt: str, user_text: str, image_path: Optional[Path] = None) -> dict:
    """Llama al modelo pidiendo una respuesta JSON y la parsea.

    Reintenta si el modelo devuelve un JSON invalido. Si tras
    MAX_RETRIES intentos sigue sin poder parsearse, levanta LLMCallError
    en vez de devolver datos inventados o a medias.
    """
    client = get_client()

    content: list = [{"type": "text", "text": user_text}]
    if image_path is not None:
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_to_data_url(image_path)},
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            last_error = exc
            logger.warning("Intento %d/%d: el modelo no devolvio JSON valido (%s).", attempt, MAX_RETRIES, exc)

    raise LLMCallError(f"El modelo no devolvio JSON valido tras {MAX_RETRIES} intentos: {last_error}")
