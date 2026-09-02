"""Etapa 3 - Analisis con el modelo (GPT-5.6 Luna).

Nivel de autonomia elegido en la Ficha de Arquitectura Cognitiva:
**Workflow / cadena** — pasos fijos en un orden predefinido, el modelo se
invoca en cada paso. Por eso esta etapa NO es un agente: es una cadena de
tres llamadas secuenciales, donde cada paso recibe el resultado del
anterior como contexto adicional.

    Paso 1  analyze_content    -> content_analysis
    Paso 2  classify_category  -> commercial_classification (usa el paso 1)
    Paso 3  assess_quality     -> quality_control            (usa los pasos 1 y 2)

Corresponde a las Etapas 3 y 4 del caso de uso ("el modelo de IA procesa
la imagen y las notas para identificar keywords" / "la IA revisa los
keywords y contexto de las fotos para determinar la categoria principal").
"""

from __future__ import annotations

import logging
from typing import List

from .llm_client import LLMCallError, call_json
from .models import (
    AnalyzedPhoto,
    CommercialClassification,
    ContentAnalysis,
    QualityControl,
    StagedPhoto,
)

logger = logging.getLogger(__name__)

CONFIDENCE_REVIEW_THRESHOLD = 0.80

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


def analyze_content(photo: StagedPhoto) -> ContentAnalysis:
    user_text = (
        "Notas del fotografo para esta imagen:\n"
        f"{photo.photographer_notes or '(sin notas)'}"
    )
    data = call_json(_CONTENT_SYSTEM_PROMPT, user_text, image_path=photo.image_path)
    return ContentAnalysis(
        primary_subject=data.get("primary_subject"),
        keywords=list(data.get("keywords") or []),
        environment=data.get("environment"),
        color_palette=list(data.get("color_palette") or []),
    )


def classify_category(photo: StagedPhoto, content: ContentAnalysis) -> CommercialClassification:
    user_text = (
        "Analisis de contenido ya extraido para esta imagen:\n"
        f"- primary_subject: {content.primary_subject}\n"
        f"- keywords: {', '.join(content.keywords)}\n"
        f"- environment: {content.environment}\n"
    )
    data = call_json(_CLASSIFICATION_SYSTEM_PROMPT, user_text, image_path=photo.image_path)
    return CommercialClassification(
        primary_category=data.get("primary_category"),
        secondary_category=data.get("secondary_category"),
    )


def assess_quality(
    photo: StagedPhoto,
    content: ContentAnalysis,
    classification: CommercialClassification,
) -> QualityControl:
    user_text = (
        "Notas originales del fotografo:\n"
        f"{photo.photographer_notes or '(sin notas)'}\n\n"
        "Analisis generado para esta imagen:\n"
        f"- primary_subject: {content.primary_subject}\n"
        f"- keywords: {', '.join(content.keywords)}\n"
        f"- environment: {content.environment}\n"
        f"- color_palette: {', '.join(content.color_palette)}\n"
        f"- primary_category: {classification.primary_category}\n"
        f"- secondary_category: {classification.secondary_category}\n"
    )
    data = call_json(_QUALITY_SYSTEM_PROMPT, user_text, image_path=photo.image_path)

    confidence = data.get("confidence_score")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    flagged = confidence is None or confidence < CONFIDENCE_REVIEW_THRESHOLD

    return QualityControl(
        confidence_score=confidence,
        flagged_for_review=flagged,
        review_reason=data.get("review_reason"),
    )


def analyze_photo(photo: StagedPhoto) -> AnalyzedPhoto:
    """Corre la cadena completa (3 llamadas) para una sola foto."""
    content = analyze_content(photo)
    classification = classify_category(photo, content)
    quality = assess_quality(photo, content, classification)

    return AnalyzedPhoto(
        photo_id=photo.photo_id,
        image_path=photo.image_path,
        photographer_notes=photo.photographer_notes,
        exif_metadata=photo.exif_metadata,
        content_analysis=content,
        commercial_classification=classification,
        quality_control=quality,
    )


def analyze_batch(photos: List[StagedPhoto]) -> List[AnalyzedPhoto]:
    """Ejecuta la Etapa 3 para todo el lote. Una foto que falle no aborta
    el resto del lote; queda registrada en el log y se salta."""
    results: List[AnalyzedPhoto] = []
    for photo in photos:
        try:
            results.append(analyze_photo(photo))
        except LLMCallError as exc:
            logger.error("Etapa 3 fallo para %s: %s", photo.image_path, exc)

    logger.info("Etapa 3 completada: %d/%d foto(s) analizada(s).", len(results), len(photos))
    return results
