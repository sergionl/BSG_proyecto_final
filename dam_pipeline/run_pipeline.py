"""Encadena la Etapa 1 (ingesta) y la Etapa 2 (EXIF) y guarda el resultado
como JSON Lines: una linea por foto, lista para que la Etapa 3 (analisis
con el modelo, todavia no implementada) la consuma.

Uso:
    python -m dam_pipeline.run_pipeline <carpeta_de_entrada> [salida.jsonl]
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dam_pipeline.etapa1_ingesta import ingest_batch
from dam_pipeline.etapa2_exif import enrich_with_exif

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def run(input_dir: str | Path, output_path: str | Path = "staging_photos.jsonl") -> Path:
    photos = ingest_batch(input_dir)
    staged = enrich_with_exif(photos)

    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        for photo in staged:
            f.write(json.dumps(photo.to_dict(), ensure_ascii=False) + "\n")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    input_dir_arg = sys.argv[1]
    output_arg = sys.argv[2] if len(sys.argv) > 2 else "staging_photos.jsonl"

    out = run(input_dir_arg, output_arg)
    print(f"Listo. {out} generado.")
