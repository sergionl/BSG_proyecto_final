"""Genera un lote de prueba (2 JPEG con EXIF + notas.txt) para validar
manualmente las Etapas 1 y 2. No es parte del pipeline, solo un fixture
de verificacion.
"""

from pathlib import Path

import piexif
from PIL import Image

FIXTURE_DIR = Path(__file__).parent / "_test_batch"


def _make_jpeg(path: Path, make: str, model: str, iso: int, fnumber, focal_len: int) -> None:
    img = Image.new("RGB", (64, 64), color=(120, 80, 40))
    exif_dict = {
        "0th": {piexif.ImageIFD.Make: make, piexif.ImageIFD.Model: model},
        "Exif": {
            piexif.ExifIFD.ISOSpeedRatings: iso,
            piexif.ExifIFD.FNumber: fnumber,
            piexif.ExifIFD.FocalLength: focal_len,
        },
    }
    exif_bytes = piexif.dump(exif_dict)
    img.save(path, exif=exif_bytes)


def build() -> Path:
    FIXTURE_DIR.mkdir(exist_ok=True)

    _make_jpeg(FIXTURE_DIR / "IMG_0001.jpg", "Sony", "ILCE-7M4", 400, (28, 10), (50, 1))
    _make_jpeg(FIXTURE_DIR / "IMG_0002.jpg", "Canon", "EOS R6", 800, (40, 10), (85, 1))

    notes = (
        "IMG_0001.jpg: Sesion de fotos matutina en la cafeteria Kafi Wasi. "
        "Cappuccino con arte latte sobre mesa de madera rustica.\n"
        "IMG_0002.jpg: Retrato en exterior, luz natural de atardecer.\n"
    )
    (FIXTURE_DIR / "notas.txt").write_text(notes, encoding="utf-8")

    return FIXTURE_DIR


if __name__ == "__main__":
    path = build()
    print(f"Fixture creado en {path}")
