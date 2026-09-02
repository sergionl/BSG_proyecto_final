"""Estructuras de datos compartidas por el pipeline (Etapas 1, 2 y 3).

Los campos siguen el esquema de salida definido en la Ficha de Caso de Uso
(PASO 5): identificacion de la foto, notas del fotografo, metadatos EXIF
tecnicos, y el analisis generado por el modelo (contenido, clasificacion
comercial y control de calidad).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional


@dataclass
class ExifMetadata:
    """Subconjunto tecnico del esquema de salida (technical_metadata)."""

    camera_brand: Optional[str] = None
    camera_model: Optional[str] = None
    iso: Optional[int] = None
    aperture: Optional[float] = None
    focal_length_mm: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IngestedPhoto:
    """Resultado de la Etapa 1: una imagen del lote emparejada con sus notas."""

    photo_id: str
    image_path: Path
    photographer_notes: str

    def to_dict(self) -> dict:
        return {
            "photo_id": self.photo_id,
            "image_path": str(self.image_path),
            "photographer_notes": self.photographer_notes,
        }


@dataclass
class StagedPhoto:
    """Resultado de la Etapa 2: la foto ingerida + su EXIF extraido.

    Este es el objeto que queda listo para la Etapa 3 (analisis con el
    modelo), que todavia no se implementa aqui.
    """

    photo_id: str
    image_path: Path
    photographer_notes: str
    exif_metadata: ExifMetadata
    exif_warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "photo_id": self.photo_id,
            "image_path": str(self.image_path),
            "photographer_notes": self.photographer_notes,
            "exif_metadata": self.exif_metadata.to_dict(),
            "exif_warnings": self.exif_warnings,
        }


@dataclass
class ContentAnalysis:
    """Paso 1 de la Etapa 3: analisis semantico y visual (content_analysis)."""

    primary_subject: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    environment: Optional[str] = None  # indoor | outdoor | studio | unknown
    color_palette: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CommercialClassification:
    """Paso 2 de la Etapa 3: clasificacion comercial (commercial_classification)."""

    primary_category: Optional[str] = None
    secondary_category: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityControl:
    """Paso 3 de la Etapa 3: control de calidad (quality_control).

    flagged_for_review se calcula en codigo a partir de confidence_score
    (no se le pide al modelo que decida el umbral), para no depender de
    que el modelo aplique la regla de forma consistente.
    """

    confidence_score: Optional[float] = None
    flagged_for_review: Optional[bool] = None
    review_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalyzedPhoto:
    """Resultado de la Etapa 3: StagedPhoto + el analisis del modelo.

    Es el objeto final del pipeline, listo para la interfaz de aprobacion
    del editor/fotografo (Etapa 6 del caso de uso).
    """

    photo_id: str
    image_path: Path
    photographer_notes: str
    exif_metadata: ExifMetadata
    content_analysis: ContentAnalysis
    commercial_classification: CommercialClassification
    quality_control: QualityControl

    def to_dict(self) -> dict:
        return {
            "photo_id": self.photo_id,
            "image_path": str(self.image_path),
            "photographer_notes": self.photographer_notes,
            "exif_metadata": self.exif_metadata.to_dict(),
            "content_analysis": self.content_analysis.to_dict(),
            "commercial_classification": self.commercial_classification.to_dict(),
            "quality_control": self.quality_control.to_dict(),
        }
