"""Etapa 6 - Revision del editor antes de aprobar y publicar.

Caso de uso (PASO 3, Etapa 6): el sistema prellena el formulario de
registro a partir de los datos obtenidos; el editor entra a hacer control
de calidad antes de aprobar y publicar.

Por ahora no hay interfaz: esto imprime el resultado de la Etapa 3 en un
formato legible por consola, a modo de placeholder de esa pantalla de
revision.
"""

from __future__ import annotations

from typing import List

from .models import AnalyzedPhoto

_WIDTH = 70


def format_photo_result(photo: AnalyzedPhoto) -> str:
    exif = photo.exif_metadata
    content = photo.content_analysis
    classification = photo.commercial_classification
    quality = photo.quality_control

    camera = " ".join(p for p in (exif.camera_brand, exif.camera_model) if p) or "-"
    aperture = f"f/{exif.aperture}" if exif.aperture is not None else "-"
    focal = f"{exif.focal_length_mm}mm" if exif.focal_length_mm is not None else "-"
    iso = exif.iso if exif.iso is not None else "-"

    keywords = ", ".join(content.keywords) if content.keywords else "-"
    colors = ", ".join(content.color_palette) if content.color_palette else "-"

    revisar = "SI" if quality.flagged_for_review else "No"
    confianza = f"{quality.confidence_score:.2f}" if quality.confidence_score is not None else "-"
    motivo = quality.review_reason or "-"

    lines = [
        "=" * _WIDTH,
        f"Foto: {photo.photo_id}  ({photo.image_path.name})",
        "=" * _WIDTH,
        "Notas del fotografo:",
        f"  {photo.photographer_notes or '(sin notas)'}",
        "",
        "Metadatos EXIF",
        f"  Camara       : {camera}",
        f"  ISO          : {iso}",
        f"  Apertura     : {aperture}",
        f"  Focal        : {focal}",
        "",
        "Analisis de contenido",
        f"  Sujeto       : {content.primary_subject or '-'}",
        f"  Ambiente     : {content.environment or '-'}",
        f"  Keywords     : {keywords}",
        f"  Colores      : {colors}",
        "",
        "Clasificacion comercial",
        f"  Categoria    : {classification.primary_category or '-'}",
        f"  Subcategoria : {classification.secondary_category or '-'}",
        "",
        "Control de calidad",
        f"  Confianza    : {confianza}",
        f"  Revisar      : {revisar}",
        f"  Motivo       : {motivo}",
        "=" * _WIDTH,
    ]
    return "\n".join(lines)


def print_photo_result(photo: AnalyzedPhoto) -> None:
    print(format_photo_result(photo))


def print_batch_results(photos: List[AnalyzedPhoto]) -> None:
    """Etapa 6: muestra todo el lote analizado para revision del editor."""
    if not photos:
        print("No hay fotos para mostrar.")
        return

    for photo in photos:
        print_photo_result(photo)
        print()

    flagged = sum(1 for p in photos if p.quality_control.flagged_for_review)
    print(f"Total: {len(photos)} foto(s) - {flagged} marcada(s) para revision.")
