"""Etapa 3: lee el staging generado por run_pipeline.py (Etapas 1+2) y
corre la cadena de analisis con el modelo sobre cada foto.

Uso:
    python -m dam_pipeline.run_analysis <staging.jsonl> [salida.jsonl]

Se separa de run_pipeline.py a proposito: Etapas 1-2 son deterministas y
gratis, Etapa 3 llama a un modelo pagado. No se quiere disparar esa
llamada como efecto colateral de correr la ingesta.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dam_pipeline.etapa3_analisis import analyze_batch
from dam_pipeline.etapa6_revision import print_batch_results
from dam_pipeline.models import ExifMetadata, StagedPhoto

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _load_staged_photos(staging_path: Path) -> list[StagedPhoto]:
    photos = []
    with staging_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            photos.append(
                StagedPhoto(
                    photo_id=row["photo_id"],
                    image_path=Path(row["image_path"]),
                    photographer_notes=row.get("photographer_notes", ""),
                    exif_metadata=ExifMetadata(**row.get("exif_metadata", {})),
                    exif_warnings=row.get("exif_warnings", []),
                )
            )
    return photos


def run(staging_path: str | Path, output_path: str | Path = "analyzed_photos.jsonl") -> Path:
    staging_path = Path(staging_path)
    photos = _load_staged_photos(staging_path)

    analyzed = analyze_batch(photos)

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        for photo in analyzed:
            f.write(json.dumps(photo.to_dict(), ensure_ascii=False) + "\n")

    # Etapa 6 (placeholder): muestra el lote para revision del editor.
    print_batch_results(analyzed)

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    staging_arg = sys.argv[1]
    output_arg = sys.argv[2] if len(sys.argv) > 2 else "analyzed_photos.jsonl"

    out = run(staging_arg, output_arg)
    print(f"Listo. {out} generado.")
