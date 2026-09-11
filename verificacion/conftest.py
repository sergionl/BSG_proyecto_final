"""Fixtures de pytest: carga .env, agrega mvp/ al sys.path, y copia las
imagenes que el dataset necesita a mvp/data/uploads/ antes de correr la
suite (mismo patron que ya usaban mvp/tests/test_security*.py)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

MVP_DIR = Path(__file__).resolve().parent.parent / "mvp"
sys.path.insert(0, str(MVP_DIR))

import config  # noqa: E402  (mvp/config.py, valida OPENAI_API_KEY y da UPLOADS_DIR)
from dataset import DATASET  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def preparar_fixtures_de_imagenes():
    """Copia cada fixture de imagen que el dataset referencia a
    mvp/data/uploads/, para que la tool los encuentre por nombre."""
    if not config.OPENAI_API_KEY:
        pytest.exit(
            "Falta OPENAI_API_KEY. Copia verificacion/.env.example a "
            "verificacion/.env y completa la clave.",
            returncode=1,
        )

    copiados = []
    for caso in DATASET:
        if caso.fixture is None:
            continue
        origen, destino_nombre = caso.fixture
        if not origen.is_file():
            pytest.exit(f"Falta el fixture {origen} para el caso {caso.id}.", returncode=1)
        destino = config.UPLOADS_DIR / destino_nombre
        shutil.copyfile(origen, destino)
        copiados.append(destino_nombre)

    yield

    # No se borran los archivos al terminar: mismo criterio que
    # mvp/tests/*, quedan disponibles para inspeccion manual despues.
