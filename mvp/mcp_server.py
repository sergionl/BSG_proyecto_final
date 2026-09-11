"""Servidor FastMCP del MVP: expone UNA sola tool, `analizar_foto`.

Migra la capacidad ya validada en el PoC (Proof_Of_Concept/dam_poc_etapas_
2_3_4_6.ipynb): Etapa 2 (EXIF por script) + Etapas 3/4 (cadena de 3 llamadas
al modelo: contenido -> clasificacion -> control de calidad). Etapa 6 (revision)
no es una tool: es responsabilidad del frontend, que muestra este resultado.

A diferencia del PoC, la respuesta de cada paso del modelo se valida contra un
esquema Pydantic (AnalisisFoto y sus sub-modelos) en vez de confiar en que
`response_format={"type": "json_object"}` + `json.loads()` alcance para
garantizar el contrato de salida.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

import exifread
import openai
from fastmcp import FastMCP
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mvp.mcp_server")

mcp = FastMCP("Catalogador de fotos DAM")

MAX_RETRIES = 2

_DIRECT_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


# --------------------------------------------------------------------------
# Contrato de salida (Pydantic) — cierra el gap detectado en el PoC: un
# prompt que "pide JSON" no garantiza que la salida cumpla el esquema.
# --------------------------------------------------------------------------

class ExifMetadata(BaseModel):
    camera_brand: Optional[str] = None
    camera_model: Optional[str] = None
    iso: Optional[int] = None
    aperture: Optional[float] = None
    focal_length_mm: Optional[int] = None


class ContentAnalysis(BaseModel):
    primary_subject: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    environment: Optional[str] = None  # indoor | outdoor | studio | unknown
    color_palette: List[str] = Field(default_factory=list)


class CommercialClassification(BaseModel):
    primary_category: Optional[str] = None
    secondary_category: Optional[str] = None


class QualityControl(BaseModel):
    confidence_score: Optional[float] = None
    flagged_for_review: Optional[bool] = None
    review_reason: Optional[str] = None


class AnalisisFoto(BaseModel):
    """Resultado de la tool `analizar_foto`. `ok=False` en cualquier error."""

    ok: bool
    fuente: str
    exif_metadata: ExifMetadata = Field(default_factory=ExifMetadata)
    content_analysis: Optional[ContentAnalysis] = None
    commercial_classification: Optional[CommercialClassification] = None
    quality_control: Optional[QualityControl] = None
    advertencias: List[str] = Field(default_factory=list)
    error: Optional[str] = None


# --------------------------------------------------------------------------
# Etapa 2 (sin IA): extraccion de EXIF, portada de dam_pipeline/etapa2_exif.py
# --------------------------------------------------------------------------

def _tag_str(tags: dict, key: str) -> Optional[str]:
    value = tags.get(key)
    return str(value).strip() if value is not None else None


def _tag_int(tags: dict, key: str) -> Optional[int]:
    value = tags.get(key)
    if value is None:
        return None
    try:
        return int(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None


def _tag_float(tags: dict, key: str) -> Optional[float]:
    value = tags.get(key)
    if value is None:
        return None
    try:
        return round(float(Fraction(str(value))), 2)
    except (ValueError, ZeroDivisionError):
        return None


def extract_exif(image_path: Path) -> tuple[ExifMetadata, List[str]]:
    warnings: List[str] = []
    with open(image_path, "rb") as f:
        tags = exifread.process_file(f, details=False)

    if not tags:
        warnings.append("El archivo no tiene datos EXIF legibles.")
        return ExifMetadata(), warnings

    metadata = ExifMetadata(
        camera_brand=_tag_str(tags, "Image Make"),
        camera_model=_tag_str(tags, "Image Model"),
        iso=_tag_int(tags, "EXIF ISOSpeedRatings"),
        aperture=_tag_float(tags, "EXIF FNumber"),
        focal_length_mm=_tag_int(tags, "EXIF FocalLength"),
    )
    for field_name, value in metadata.model_dump().items():
        if value is None:
            warnings.append(f"Tag EXIF faltante para '{field_name}'.")
    return metadata, warnings


# --------------------------------------------------------------------------
# Etapas 3/4 (con IA): cadena de 3 llamadas, portada de
# dam_pipeline/etapa3_analisis.py + dam_pipeline/llm_client.py
# --------------------------------------------------------------------------

_CONTENT_SYSTEM_PROMPT = """
Eres un analista visual para un DAM (Digital Asset Management) de fotografia.
Tu tarea es analizar UNA fotografia junto a las notas sueltas del fotografo
y describir su contenido. No inventes detalles que no se vean en la imagen
ni esten respaldados por las notas.

Devuelve UNICAMENTE un objeto JSON con este esquema, sin texto adicional:
{
  "primary_subject": "string, breve y concreto",
  "keywords": ["10 a 15 terminos descriptivos en espanol: objetos, ambiente, estilo, uso comercial. Sin 'foto' ni 'imagen'."],
  "environment": "uno de: indoor | outdoor | studio | unknown",
  "color_palette": ["3 a 5 colores dominantes, como codigo hex o nombre estandar"]
}
""".strip()

_CLASSIFICATION_SYSTEM_PROMPT = """
Eres un clasificador comercial de fotografia para un DAM. Recibes la imagen
y el analisis de contenido ya extraido (sujeto, keywords, ambiente). Con
eso, asigna la categoria comercial mas adecuada.

Categorias sugeridas (usa la que mejor calce; puedes usar otra si ninguna
aplica bien): Food & Beverage, Lifestyle, Corporate, Nature, Technology,
Architecture, Fashion, Travel.

Devuelve UNICAMENTE un objeto JSON con este esquema, sin texto adicional:
{
  "primary_category": "string",
  "secondary_category": "string, o null si no aplica una subcategoria clara"
}
""".strip()

_QUALITY_SYSTEM_PROMPT = """
Eres un revisor de control de calidad para un DAM. Recibes las notas
originales del fotografo, la imagen, y el analisis + clasificacion que ya
se generaron para esta foto. Evalua que tan coherente es ese analisis con
la imagen real y con las notas.

Devuelve UNICAMENTE un objeto JSON con este esquema, sin texto adicional:
{
  "confidence_score": "float entre 0.00 y 1.00, segun la coherencia entre notas, imagen y el analisis generado",
  "review_reason": "string breve explicando dudas o contradicciones, o null si no hay ninguna"
}

No decidas tu mismo si hay que marcar la foto para revision: eso lo
calcula el sistema a partir del confidence_score que devuelvas.
""".strip()


class LLMCallError(RuntimeError):
    """El modelo no devolvio una respuesta usable tras los reintentos."""


_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise LLMCallError(
                "Falta OPENAI_API_KEY. Copia .env.example a .env y completa la clave."
            )
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _image_to_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    mime = _DIRECT_IMAGE_TYPES.get(suffix) or mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    raw_bytes = image_path.read_bytes()
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _call_json(system_prompt: str, user_text: str, image_path: Path) -> dict:
    import json

    client = _get_client()
    content: list = [
        {"type": "text", "text": user_text},
        {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path)}},
    ]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=config.MODEL_ID,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except openai.BadRequestError as exc:
            # Error del cliente (ej. formato de imagen invalido): no es
            # transitorio, reintentar no ayuda. Se traduce a LLMCallError
            # para que analizar_foto lo devuelva como ok=False, en vez de
            # dejar que la excepcion cruda se escape del contrato de la tool.
            raise LLMCallError(f"La API del modelo rechazo la solicitud: {exc}") from exc
        except openai.APIError as exc:
            # Errores de red/servidor si pueden ser transitorios: se
            # reintenta dentro del mismo bucle.
            last_error = exc
            logger.warning("Intento %d/%d: error de API (%s).", attempt, MAX_RETRIES, exc)
            continue

        raw = response.choices[0].message.content
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            last_error = exc
            logger.warning("Intento %d/%d: JSON invalido (%s).", attempt, MAX_RETRIES, exc)

    raise LLMCallError(f"El modelo no devolvio una respuesta usable tras {MAX_RETRIES} intentos: {last_error}")


def _validate_step(model_cls, raw: dict, warnings: List[str], step_name: str):
    """Valida la respuesta del modelo contra el esquema Pydantic esperado.

    Si el modelo devuelve campos con tipos o nombres distintos al contrato,
    esto lo detecta aqui (a diferencia del PoC, que solo hacia json.loads).
    """
    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        warnings.append(f"Salida de '{step_name}' no cumplio el esquema esperado: {exc.error_count()} error(es).")
        logger.warning("Validacion fallida en %s: %s", step_name, exc)
        # Best-effort: construir el modelo solo con los campos que si son validos.
        cleaned = {k: v for k, v in raw.items() if k in model_cls.model_fields}
        try:
            return model_cls.model_validate(cleaned)
        except ValidationError:
            return model_cls()


def _analizar_con_modelo(image_path: Path, notas: str, warnings: List[str]) -> tuple[
    ContentAnalysis, CommercialClassification, QualityControl
]:
    user_text_1 = f"Notas del fotografo para esta imagen:\n{notas or '(sin notas)'}"
    raw_content = _call_json(_CONTENT_SYSTEM_PROMPT, user_text_1, image_path)
    content = _validate_step(ContentAnalysis, raw_content, warnings, "content_analysis")

    user_text_2 = (
        "Analisis de contenido ya extraido para esta imagen:\n"
        f"- primary_subject: {content.primary_subject}\n"
        f"- keywords: {', '.join(content.keywords)}\n"
        f"- environment: {content.environment}\n"
    )
    raw_classification = _call_json(_CLASSIFICATION_SYSTEM_PROMPT, user_text_2, image_path)
    classification = _validate_step(
        CommercialClassification, raw_classification, warnings, "commercial_classification"
    )

    user_text_3 = (
        "Notas originales del fotografo:\n"
        f"{notas or '(sin notas)'}\n\n"
        "Analisis generado para esta imagen:\n"
        f"- primary_subject: {content.primary_subject}\n"
        f"- keywords: {', '.join(content.keywords)}\n"
        f"- environment: {content.environment}\n"
        f"- color_palette: {', '.join(content.color_palette)}\n"
        f"- primary_category: {classification.primary_category}\n"
        f"- secondary_category: {classification.secondary_category}\n"
    )
    raw_quality = _call_json(_QUALITY_SYSTEM_PROMPT, user_text_3, image_path)
    quality = _validate_step(QualityControl, raw_quality, warnings, "quality_control")

    confidence = quality.confidence_score
    quality.flagged_for_review = confidence is None or confidence < config.CONFIDENCE_REVIEW_THRESHOLD

    return content, classification, quality


# --------------------------------------------------------------------------
# La tool MCP
# --------------------------------------------------------------------------

@mcp.tool
def analizar_foto(image_path: str, notas: str = "") -> dict:
    """Analiza una fotografia ya subida al servidor junto con las notas del
    fotografo: extrae metadatos EXIF, identifica sujeto/ambiente/paleta de
    colores/keywords, clasifica la categoria comercial y evalua la confianza
    del analisis (marcando para revision humana si es baja o ambigua).

    Usa esta tool siempre que se pida catalogar, analizar o generar keywords
    para una fotografia subida al sistema. Es de solo lectura: no modifica,
    mueve ni borra ningun archivo. No sirve para decidir licencias o derechos
    de uso de una imagen (eso queda fuera de alcance de este sistema).

    Parameters
    ----------
    image_path: ruta del archivo de imagen dentro de la carpeta de subidas
        del servidor (nunca una ruta arbitraria del sistema).
    notas: notas sueltas del fotografo sobre la foto, o cadena vacia.
    """
    warnings: List[str] = []

    resolved = (config.UPLOADS_DIR / Path(image_path).name).resolve()
    if config.UPLOADS_DIR.resolve() not in resolved.parents and resolved != config.UPLOADS_DIR.resolve():
        return AnalisisFoto(
            ok=False, fuente=str(image_path), error="Ruta de imagen no permitida."
        ).model_dump()

    if not resolved.is_file():
        return AnalisisFoto(
            ok=False, fuente=resolved.name, error=f"No existe el archivo: {resolved.name}"
        ).model_dump()

    if resolved.suffix.lower() not in _DIRECT_IMAGE_TYPES:
        return AnalisisFoto(
            ok=False,
            fuente=resolved.name,
            error=f"Formato no soportado en el MVP: {resolved.suffix}. Usa jpg/jpeg/png/webp.",
        ).model_dump()

    try:
        exif_metadata, exif_warnings = extract_exif(resolved)
        warnings.extend(exif_warnings)
    except Exception as exc:  # archivo corrupto, formato inesperado, etc.
        logger.warning("No se pudo leer EXIF de %s: %s", resolved, exc)
        exif_metadata = ExifMetadata()
        warnings.append(f"Error al leer EXIF: {exc}")

    try:
        content, classification, quality = _analizar_con_modelo(resolved, notas, warnings)
    except LLMCallError as exc:
        return AnalisisFoto(
            ok=False,
            fuente=resolved.name,
            exif_metadata=exif_metadata,
            advertencias=warnings,
            error=str(exc),
        ).model_dump()

    return AnalisisFoto(
        ok=True,
        fuente=resolved.name,
        exif_metadata=exif_metadata,
        content_analysis=content,
        commercial_classification=classification,
        quality_control=quality,
        advertencias=warnings,
    ).model_dump()
