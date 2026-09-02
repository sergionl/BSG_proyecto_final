"""Etapa 2 - Extraccion de metadatos EXIF.

Caso de uso (PASO 3, Etapa 2): hoy el editor/fotografo abre las
propiedades de cada imagen y transcribe los datos EXIF a mano. Aqui no
interviene la IA: se reemplaza esa transcripcion manual por un script que
lee el EXIF directamente del archivo.

Usa `exifread` porque, a diferencia de Pillow, lee tanto JPEG como los
formatos RAW mas comunes (CR2, NEF, ARW, DNG, ...), que es el rango de
entrada declarado en la Ficha de Caso de Uso ("raw/jpeg/jpg").
"""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import List

import exifread

from .models import ExifMetadata, IngestedPhoto, StagedPhoto

logger = logging.getLogger(__name__)


def _tag_str(tags: dict, key: str) -> str | None:
    value = tags.get(key)
    return str(value).strip() if value is not None else None


def _tag_int(tags: dict, key: str) -> int | None:
    value = tags.get(key)
    if value is None:
        return None
    try:
        return int(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None


def _tag_float(tags: dict, key: str) -> float | None:
    value = tags.get(key)
    if value is None:
        return None
    try:
        return round(float(Fraction(str(value))), 2)
    except (ValueError, ZeroDivisionError):
        return None


def extract_exif(image_path: str | Path) -> tuple[ExifMetadata, List[str]]:
    """Lee el EXIF de una imagen y lo mapea al esquema tecnico del proyecto.

    Devuelve la metadata encontrada y una lista de advertencias (por
    ejemplo, tags ausentes) para que la Etapa 2 nunca falle por un EXIF
    incompleto: los campos faltantes quedan en None, siguiendo la politica
    de "nunca inventar" de la Ficha 1.
    """
    image_path = Path(image_path)
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

    for field_name, value in metadata.to_dict().items():
        if value is None:
            warnings.append(f"Tag EXIF faltante para '{field_name}'.")

    return metadata, warnings


def enrich_with_exif(photos: List[IngestedPhoto]) -> List[StagedPhoto]:
    """Ejecuta la Etapa 2 sobre la salida de la Etapa 1."""
    staged: List[StagedPhoto] = []

    for photo in photos:
        try:
            metadata, warnings = extract_exif(photo.image_path)
        except Exception as exc:  # archivo corrupto, formato no soportado, etc.
            logger.warning("No se pudo leer EXIF de %s: %s", photo.image_path, exc)
            metadata, warnings = ExifMetadata(), [f"Error al leer EXIF: {exc}"]

        staged.append(
            StagedPhoto(
                photo_id=photo.photo_id,
                image_path=photo.image_path,
                photographer_notes=photo.photographer_notes,
                exif_metadata=metadata,
                exif_warnings=warnings,
            )
        )

    logger.info("Etapa 2 completada: EXIF procesado para %d foto(s).", len(staged))
    return staged
