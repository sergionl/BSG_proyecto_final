"""Manejo de notas del fotografo: extraccion de texto (.txt/.docx/.pdf) y
emparejamiento con cada foto de un lote subido.

El emparejamiento por nombre de archivo esta portado de
dam_pipeline/etapa1_ingesta.py (Etapa 1 del PoC): si las notas traen el
formato "nombre_archivo.jpg: notas...", se asignan por foto; si no, se
intenta por bloques en el mismo orden que las fotos; si tampoco calza, se
usa el texto completo como nota para todas las fotos del lote.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Dict, List, Optional

SUPPORTED_NOTE_EXTENSIONS = {".txt", ".docx", ".pdf"}


class NotesExtractionError(ValueError):
    """Formato de archivo de notas no soportado o archivo ilegible."""


def _extract_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise NotesExtractionError(f"No se pudo leer el .docx de notas: {exc}") from exc

    xml = xml.replace("</w:p>", "</w:p>\n")
    text = re.sub(r"<[^>]+>", "", xml)
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        raw = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # PDF corrupto, cifrado, etc.
        raise NotesExtractionError(f"No se pudo leer el .pdf de notas: {exc}") from exc

    # pypdf a veces separa palabras con tabs segun el espaciado del PDF
    # (sobre todo en titulos con tipografia grande); normalizamos a espacios.
    return re.sub(r"[ \t]+", " ", raw)


def extract_notes_text(filename: str, data: bytes) -> str:
    """Extrae el texto plano de un archivo de notas (.txt, .docx o .pdf)."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    suffix = f".{suffix}"

    if suffix == ".txt":
        return _extract_txt(data)
    if suffix == ".docx":
        return _extract_docx(data)
    if suffix == ".pdf":
        return _extract_pdf(data)

    raise NotesExtractionError(
        f"Formato de notas no soportado: '{suffix}'. Usa .txt, .docx o .pdf."
    )


_FILENAME_LIKE = re.compile(r"^[\w\-. ]+\.[A-Za-z]{2,5}$")


def _parse_tagged_notes(raw_text: str, image_names: List[str]) -> Optional[Dict[str, str]]:
    """Notas en formato "nombre_archivo.jpg: notas...".

    El archivo de notas puede traer entradas para MAS fotos de las que se
    subieron en este lote (p.ej. un notas.txt compartido para toda una
    sesion, pero el usuario solo sube 2 de esas fotos ahora). Si una linea
    parece un tag de archivo (tiene pinta de nombre de archivo + extension)
    pero no esta en este lote, se corta la asignacion en curso para no
    "pegar" esas notas ajenas a la foto anterior.
    """
    lookup = {name.lower(): name for name in image_names}
    notes_by_image: Dict[str, str] = {}
    current_key: Optional[str] = None

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        head, sep, rest = stripped.partition(":")
        candidate = head.strip().lower()
        if sep and candidate in lookup:
            current_key = lookup[candidate]
            notes_by_image[current_key] = rest.strip()
        elif sep and _FILENAME_LIKE.match(candidate):
            # Tag de una foto que no esta en este lote: no continuar
            # acumulando en la foto anterior.
            current_key = None
        elif current_key is not None:
            notes_by_image[current_key] = (notes_by_image[current_key] + " " + stripped).strip()

    return notes_by_image or None


def _parse_blocks_in_order(raw_text: str, image_names: List[str]) -> Optional[Dict[str, str]]:
    blocks = [b.strip() for b in raw_text.split("\n\n") if b.strip()]
    if len(blocks) != len(image_names):
        return None
    return dict(zip(image_names, blocks))


def match_notes_to_photos(raw_text: str, image_names: List[str]) -> Dict[str, str]:
    """Empareja el texto de notas (ya extraido) con cada foto del lote.

    Estrategia (misma que Etapa 1 del PoC):
    1. Etiquetado por archivo: "nombre.jpg: notas..." por linea.
    2. Bloques separados por linea en blanco, en el mismo orden que las fotos.
    3. Si nada calza, la misma nota completa se aplica a todas las fotos.
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {name: "" for name in image_names}

    tagged = _parse_tagged_notes(raw_text, image_names)
    if tagged is not None:
        for name in image_names:
            tagged.setdefault(name, "")
        return tagged

    by_blocks = _parse_blocks_in_order(raw_text, image_names)
    if by_blocks is not None:
        return by_blocks

    return {name: raw_text for name in image_names}
