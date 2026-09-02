"""Etapa 1 - Ingesta del lote.

Caso de uso (PASO 3, Etapa 1): "El fotografo sube una carpeta con las
imagenes y un archivo de notas sueltas en texto plano". No interviene la
IA: el sistema solo detecta la carga y extrae imagenes y notas.

Formato de notas soportado
---------------------------
El archivo de notas (.txt) puede venir en dos formatos:

1. Etiquetado por archivo (recomendado): cada linea empieza con el nombre
   del archivo de imagen seguido de ":" y las notas de esa foto.

       IMG_0001.jpg: Sesion matutina en la cafeteria, luz natural.
       IMG_0002.jpg: Mismo set, toma cenital de la taza.

2. Bloques en orden: si no hay nombres de archivo, el texto se separa por
   lineas en blanco y cada bloque se asigna en orden a las imagenes
   ordenadas alfabeticamente. Si el numero de bloques no coincide con el
   numero de imagenes, se usa el archivo completo como nota para todas las
   fotos (con una advertencia).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Dict, List

from .models import IngestedPhoto

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg",  # comprimidas
    ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2",  # raw comunes
}


class IngestError(ValueError):
    """Carpeta de entrada invalida o vacia para la Etapa 1."""


def _new_photo_id() -> str:
    return uuid.uuid4().hex[:10]


def _find_images(input_dir: Path) -> List[Path]:
    images = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    return images


def _find_notes_file(input_dir: Path) -> Path | None:
    txt_files = sorted(input_dir.glob("*.txt"))
    if not txt_files:
        return None
    if len(txt_files) > 1:
        logger.warning(
            "Se encontraron %d archivos .txt en %s; se usa el primero (%s).",
            len(txt_files), input_dir, txt_files[0].name,
        )
    return txt_files[0]


def _parse_tagged_notes(raw_text: str, image_names: List[str]) -> Dict[str, str] | None:
    """Intenta el formato 'nombre_archivo.jpg: notas...'. None si no aplica."""
    lookup = {name.lower(): name for name in image_names}
    notes_by_image: Dict[str, str] = {}
    current_key: str | None = None

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        head, sep, rest = stripped.partition(":")
        candidate = head.strip().lower()
        if sep and candidate in lookup:
            current_key = lookup[candidate]
            notes_by_image[current_key] = rest.strip()
        elif current_key is not None:
            notes_by_image[current_key] = (notes_by_image[current_key] + " " + stripped).strip()

    if not notes_by_image:
        return None
    return notes_by_image


def _parse_blocks_in_order(raw_text: str, image_names: List[str]) -> Dict[str, str] | None:
    blocks = [b.strip() for b in raw_text.split("\n\n") if b.strip()]
    if len(blocks) != len(image_names):
        return None
    return dict(zip(image_names, blocks))


def _parse_notes(notes_path: Path | None, image_names: List[str]) -> Dict[str, str]:
    if notes_path is None:
        logger.warning("No se encontro archivo de notas (.txt); se ingresa con notas vacias.")
        return {name: "" for name in image_names}

    raw_text = notes_path.read_text(encoding="utf-8", errors="replace")

    tagged = _parse_tagged_notes(raw_text, image_names)
    if tagged is not None:
        for name in image_names:
            tagged.setdefault(name, "")
        return tagged

    by_blocks = _parse_blocks_in_order(raw_text, image_names)
    if by_blocks is not None:
        return by_blocks

    logger.warning(
        "No se pudo emparejar el archivo de notas por imagen; se asigna el "
        "texto completo a todas las fotos del lote."
    )
    return {name: raw_text.strip() for name in image_names}


def ingest_batch(input_dir: str | Path) -> List[IngestedPhoto]:
    """Ejecuta la Etapa 1: lee la carpeta del lote y arma un IngestedPhoto
    por cada imagen, con su nota asociada.

    Parameters
    ----------
    input_dir:
        Carpeta subida por el fotografo. Debe contener las imagenes del
        lote y, opcionalmente, un archivo .txt con las notas.
    """
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise IngestError(f"La carpeta de entrada no existe: {input_dir}")

    images = _find_images(input_dir)
    if not images:
        raise IngestError(f"No se encontraron imagenes en: {input_dir}")

    notes_path = _find_notes_file(input_dir)
    notes_by_name = _parse_notes(notes_path, [img.name for img in images])

    ingested = [
        IngestedPhoto(
            photo_id=_new_photo_id(),
            image_path=img,
            photographer_notes=notes_by_name.get(img.name, ""),
        )
        for img in images
    ]

    logger.info("Etapa 1 completada: %d foto(s) ingerida(s) desde %s.", len(ingested), input_dir)
    return ingested
