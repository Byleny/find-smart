import os
import sys
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

# La base de datos de pruebas se configura antes de importar la app, porque
# database.py crea el engine al importarse.
_TMP = Path(tempfile.mkdtemp(prefix="finsmart_tests_"))
RUTA_BD_PRUEBAS = _TMP / "test.db"
CLAVE_BD_PRUEBAS = "clave-cifrado-pruebas-finsmart"
os.environ["DATABASE_URL"] = f"sqlite:///{RUTA_BD_PRUEBAS.as_posix()}"
# Toda la suite corre sobre la base cifrada con SQLCipher, como en un despliegue con DB_ENCRYPTION_KEY.
os.environ["DB_ENCRYPTION_KEY"] = CLAVE_BD_PRUEBAS
os.environ["SECRET_KEY"] = "clave-de-pruebas-finsmart-con-mas-de-32-caracteres"
for _var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "TWOCAPTCHA_API_KEY"):
    os.environ[_var] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from database import Base, engine  # noqa: E402
from main import app  # noqa: E402
from security import limitador_login, limitador_miembros  # noqa: E402
import services.ml_service as ml_service  # noqa: E402


@pytest.fixture(autouse=True)
def base_limpia():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    limitador_login._fallos.clear()
    limitador_miembros._fallos.clear()
    yield


@pytest.fixture(autouse=True)
def modelos_aislados(tmp_path, monkeypatch):
    # Los modelos entrenados en las pruebas no deben tocar backend/ml_models.
    monkeypatch.setattr(ml_service, "MODEL_DIR", tmp_path)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def registrar(client, email=None, password="ClaveSegura123", nombre="Usuario Prueba"):
    email = email or f"user_{uuid.uuid4().hex[:8]}@finsmart.co"
    r = client.post("/auth/register", json={"acepta_politica": True, "email": email, "password": password, "full_name": nombre})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest.fixture
def usuario(client):
    headers, _ = registrar(client)
    return headers


@pytest.fixture
def otro_usuario(client):
    headers, _ = registrar(client)
    return headers


def gasto(client, headers, descripcion="Mercado", monto=38000, categoria="Alimentación", fecha=None, tipo="gasto"):
    fecha = fecha or date.today()
    return client.post(
        "/transactions",
        json={"description": descripcion, "amount": monto, "category": categoria,
              "type": tipo, "date": fecha.isoformat()},
        headers=headers,
    )


def historial_entrenable(client, headers):
    """Doce gastos en tres categorías, suficiente para entrenar ambos modelos."""
    hoy = date.today()
    datos = [
        ("Uber viaje", 15000, "Transporte"), ("Uber aeropuerto", 22000, "Transporte"),
        ("Taxi centro", 12000, "Transporte"), ("Uber noche", 18000, "Transporte"),
        ("Netflix suscripcion", 38900, "Entretenimiento"), ("Cine Colombia", 25000, "Entretenimiento"),
        ("Spotify premium", 16900, "Entretenimiento"), ("Netflix plan", 38900, "Entretenimiento"),
        ("Mercado Exito", 120000, "Alimentación"), ("Mercado D1", 85000, "Alimentación"),
        ("Domicilio comida", 32000, "Alimentación"), ("Mercado mensual", 140000, "Alimentación"),
    ]
    for i, (d, m, c) in enumerate(datos):
        r = gasto(client, headers, d, m, c, hoy - timedelta(days=i))
        assert r.status_code == 201, r.text
