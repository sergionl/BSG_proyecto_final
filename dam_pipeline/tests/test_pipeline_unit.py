"""Tests unitarios de Etapa 1 (ingesta) y Etapa 2 (EXIF): nada de red, nada
de API, corren gratis en CI en cada push. La Etapa 3 (llamadas al modelo) no
tiene equivalente aqui a proposito -- eso vive en mvp/tests/test_smoke.py y
solo se corre manualmente (tiene costo real), ver .github/workflows/.

Usa imagenes JPEG sinteticas con EXIF real generadas en el momento (via
piexif), no fotos del repo -- asi el test no depende de datos personales ni
se rompe si alguien reemplaza fotos/.
"""

from __future__ import annotations

import pytest

from dam_pipeline._make_test_fixtures import _make_jpeg
from dam_pipeline.etapa1_ingesta import IngestError, ingest_batch
from dam_pipeline.etapa2_exif import enrich_with_exif, extract_exif


def _build_batch(tmp_path):
    _make_jpeg(tmp_path / "IMG_0001.jpg", "Sony", "ILCE-7M4", 400, (28, 10), (50, 1))
    _make_jpeg(tmp_path / "IMG_0002.jpg", "Canon", "EOS R6", 800, (40, 10), (85, 1))
    (tmp_path / "notas.txt").write_text(
        "IMG_0001.jpg: Sesion matutina en la cafeteria.\n"
        "IMG_0002.jpg: Retrato en exterior, luz natural.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_ingest_batch_empareja_notas_por_archivo(tmp_path):
    _build_batch(tmp_path)
    photos = ingest_batch(tmp_path)

    assert len(photos) == 2
    notas_por_nombre = {p.image_path.name: p.photographer_notes for p in photos}
    assert notas_por_nombre["IMG_0001.jpg"] == "Sesion matutina en la cafeteria."
    assert notas_por_nombre["IMG_0002.jpg"] == "Retrato en exterior, luz natural."


def test_ingest_batch_sin_notas_usa_texto_vacio(tmp_path):
    _make_jpeg(tmp_path / "IMG_0001.jpg", "Sony", "ILCE-7M4", 400, (28, 10), (50, 1))
    photos = ingest_batch(tmp_path)

    assert len(photos) == 1
    assert photos[0].photographer_notes == ""


def test_ingest_batch_falla_sin_imagenes(tmp_path):
    (tmp_path / "notas.txt").write_text("no hay fotos aca", encoding="utf-8")

    with pytest.raises(IngestError):
        ingest_batch(tmp_path)


def test_ingest_batch_falla_si_la_carpeta_no_existe(tmp_path):
    with pytest.raises(IngestError):
        ingest_batch(tmp_path / "no_existe")


def test_extract_exif_lee_metadata_real(tmp_path):
    img_path = tmp_path / "foto.jpg"
    _make_jpeg(img_path, "Sony", "ILCE-7M4", 400, (28, 10), (50, 1))

    metadata, warnings = extract_exif(img_path)

    assert metadata.camera_brand == "Sony"
    assert metadata.camera_model == "ILCE-7M4"
    assert metadata.iso == 400
    assert metadata.aperture == 2.8
    assert metadata.focal_length_mm == 50
    assert warnings == []


def test_extract_exif_sin_datos_reporta_advertencias(tmp_path):
    from PIL import Image

    img_path = tmp_path / "sin_exif.jpg"
    Image.new("RGB", (32, 32), color=(10, 10, 10)).save(img_path)

    metadata, warnings = extract_exif(img_path)

    assert metadata.camera_brand is None
    assert warnings  # al menos una advertencia por datos faltantes


def test_enrich_with_exif_sobre_lote_completo(tmp_path):
    _build_batch(tmp_path)
    photos = ingest_batch(tmp_path)

    staged = enrich_with_exif(photos)

    assert len(staged) == 2
    marcas = {s.exif_metadata.camera_brand for s in staged}
    assert marcas == {"Sony", "Canon"}
