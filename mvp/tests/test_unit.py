"""Tests unitarios: nada de llamadas a la API de OpenAI, corren gratis en
CI en cada push (ver .github/workflows/ci.yml).

Cubre notes.py (extraccion y emparejamiento de notas, logica pura) y las
rutas de mcp_server.analizar_foto que fallan ANTES de tocar el modelo
(archivo inexistente, path traversal, formato no soportado) + extraccion
de EXIF sobre una foto real del repo.

Los tests que SI llaman al modelo real (test_smoke.py, test_security.py,
test_security_visual.py) tienen costo y NO corren aca a proposito: viven
en un workflow de CI separado, disparado a mano.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import config  # noqa: E402
import mcp_server  # noqa: E402
import notes  # noqa: E402

FOTOS = Path(__file__).resolve().parent.parent.parent / "fotos"


# --------------------------------------------------------------------
# notes.py: extraccion y emparejamiento -- logica pura, sin red
# --------------------------------------------------------------------

def test_extract_notes_text_txt():
    texto = notes.extract_notes_text("notas.txt", "Hola con tildes: café".encode("utf-8"))
    assert texto == "Hola con tildes: café"


def test_extract_notes_text_formato_no_soportado():
    with pytest.raises(notes.NotesExtractionError):
        notes.extract_notes_text("notas.xlsx", b"contenido")


def test_match_notes_etiquetado_por_archivo():
    fotos = ["Foto1.JPEG", "Foto2.jpeg", "Foto3.jpg"]
    crudo = "Foto1.JPEG: Nota uno\n\nFoto2.jpeg: Nota dos\n\nFoto3.jpg: Nota tres"

    resultado = notes.match_notes_to_photos(crudo, fotos)

    assert resultado["Foto2.jpeg"] == "Nota dos"


def test_match_notes_no_arrastra_tags_de_fotos_fuera_del_lote():
    """Regresion de un bug real: un notas.txt con mas fotos de las
    subidas no debe pegar la nota de una foto ajena a la anterior del
    lote (encontrado y corregido durante el desarrollo del MVP)."""
    fotos = ["Foto2.jpeg", "Foto4.jpeg"]
    crudo = (
        "Foto1.JPEG: Nota de una foto que no se subio\n\n"
        "Foto2.jpeg: Perro blanco llamado Pecas\n\n"
        "Foto3.jpg: Otra nota de una foto no subida"
    )

    resultado = notes.match_notes_to_photos(crudo, fotos)

    assert resultado["Foto2.jpeg"] == "Perro blanco llamado Pecas"
    assert resultado["Foto4.jpeg"] == ""


def test_match_notes_bloques_en_orden():
    fotos = ["a.jpg", "b.jpg"]
    resultado = notes.match_notes_to_photos("Primer bloque.\n\nSegundo bloque.", fotos)
    assert resultado == {"a.jpg": "Primer bloque.", "b.jpg": "Segundo bloque."}


def test_match_notes_texto_generico_aplica_a_todas():
    fotos = ["a.jpg", "b.jpg", "c.jpg"]
    resultado = notes.match_notes_to_photos("Una sola nota para todas.", fotos)
    assert all(v == "Una sola nota para todas." for v in resultado.values())


def test_match_notes_vacio():
    assert notes.match_notes_to_photos("", ["a.jpg"]) == {"a.jpg": ""}


# --------------------------------------------------------------------
# mcp_server.analizar_foto: rutas que fallan ANTES de llamar al modelo
# --------------------------------------------------------------------

@pytest.fixture
def foto_real_subida():
    origen = FOTOS / "Foto1.JPEG"
    destino = config.UPLOADS_DIR / "test_unit_Foto1.JPEG"
    destino.write_bytes(origen.read_bytes())
    yield destino.name
    destino.unlink(missing_ok=True)


def test_analizar_foto_archivo_inexistente():
    resultado = mcp_server.analizar_foto("no_existe_de_verdad.jpg", "notas")
    assert resultado["ok"] is False
    assert "no existe" in resultado["error"].lower()


def test_analizar_foto_path_traversal_no_escapa_de_uploads():
    resultado = mcp_server.analizar_foto("../../.env", "notas")
    # Path(...).name recorta a solo ".env": nunca puede escapar de
    # uploads/, por eso el resultado es "no existe" y no otra cosa.
    assert resultado["ok"] is False
    assert resultado["fuente"] == ".env"


def test_analizar_foto_formato_no_soportado():
    archivo = config.UPLOADS_DIR / "test_unit_nota.txt"
    archivo.write_text("esto no es una imagen", encoding="utf-8")
    try:
        resultado = mcp_server.analizar_foto("test_unit_nota.txt", "")
        assert resultado["ok"] is False
        assert "no soportado" in resultado["error"].lower()
    finally:
        archivo.unlink(missing_ok=True)


def test_extract_exif_con_foto_real_del_repo(foto_real_subida):
    metadata, warnings = mcp_server.extract_exif(config.UPLOADS_DIR / foto_real_subida)
    assert metadata.camera_brand == "Apple"
    assert metadata.camera_model == "iPhone 16"
    assert warnings == []
