"""RNF-02: límite de intentos, cifrado en reposo, enumeración de cuentas y manejo de errores."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import bcrypt
import pytest
from fastapi.testclient import TestClient

import routers.auth as auth_router
import routers.recurring as recurring_router
from conftest import registrar, gasto, RUTA_BD_PRUEBAS, CLAVE_BD_PRUEBAS
from cifrar_base_de_datos import cifrar
from database import build_database_url, engine
from main import app
from security import limitador_login, limitador_miembros


def login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


# ── Límite de intentos ────────────────────────────────────────────────────────

def test_PF_SEG_01_cuenta_se_bloquea_tras_cinco_intentos_fallidos(client):
    _, email = registrar(client, password="ClaveSegura123")
    for _ in range(5):
        assert login(client, email, "Incorrecta1").status_code == 401
    bloqueado = login(client, email, "ClaveSegura123")
    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["Retry-After"]) > 0


def test_PF_SEG_02_el_bloqueo_es_por_cuenta(client):
    _, email_a = registrar(client, password="ClaveSegura123")
    _, email_b = registrar(client, password="ClaveSegura123")
    for _ in range(5):
        login(client, email_a, "Incorrecta1")
    assert login(client, email_a, "ClaveSegura123").status_code == 429
    assert login(client, email_b, "ClaveSegura123").status_code == 200


def test_PF_SEG_03_inicio_exitoso_reinicia_el_contador(client):
    _, email = registrar(client, password="ClaveSegura123")
    for _ in range(4):
        login(client, email, "Incorrecta1")
    assert login(client, email, "ClaveSegura123").status_code == 200
    for _ in range(4):
        login(client, email, "Incorrecta1")
    assert login(client, email, "ClaveSegura123").status_code == 200


def test_PF_SEG_04_el_bloqueo_expira_al_terminar_la_ventana(client, monkeypatch):
    reloj = {"t": 1000.0}
    monkeypatch.setattr(limitador_login, "reloj", lambda: reloj["t"])
    _, email = registrar(client, password="ClaveSegura123")
    for _ in range(5):
        login(client, email, "Incorrecta1")
    assert login(client, email, "ClaveSegura123").status_code == 429
    reloj["t"] += limitador_login.ventana + 1
    assert login(client, email, "ClaveSegura123").status_code == 200


# ── Cifrado en reposo ─────────────────────────────────────────────────────────

def test_PF_SEG_05_el_archivo_de_la_base_no_contiene_datos_legibles(client, usuario):
    gasto(client, usuario, "SECRETO-FINSMART-12345", 777777)
    engine.dispose()  # asegura que todo quede escrito en el archivo
    contenido = RUTA_BD_PRUEBAS.read_bytes()
    assert b"SECRETO-FINSMART-12345" not in contenido
    assert not contenido.startswith(b"SQLite format 3")


def test_PF_SEG_06_sin_la_clave_la_base_no_se_puede_abrir(client, usuario):
    gasto(client, usuario)
    engine.dispose()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(RUTA_BD_PRUEBAS).execute("SELECT * FROM transactions").fetchall()


def test_PU_SEG_07_url_de_conexion_con_y_sin_clave():
    assert build_database_url("sqlite:///./finsmart.db", "") == "sqlite:///./finsmart.db"
    assert build_database_url("sqlite:///./data/f.db", "a b/c") == "sqlite+pysqlcipher://:a%20b%2Fc@/./data/f.db"
    with pytest.raises(ValueError):
        build_database_url("postgresql://u@h/db", "clave")


def test_PU_SEG_08_migracion_de_una_base_sin_cifrar(tmp_path):
    origen = tmp_path / "plana.db"
    destino = tmp_path / "cifrada.db"
    con = sqlite3.connect(origen)
    con.execute("CREATE TABLE transactions (id INTEGER, description TEXT)")
    con.executemany("INSERT INTO transactions VALUES (?, ?)", [(1, "arriendo"), (2, "mercado")])
    con.commit()
    con.close()

    filas = cifrar(str(origen), str(destino), CLAVE_BD_PRUEBAS)

    assert filas == {"transactions": 2}
    assert b"arriendo" in origen.read_bytes()
    assert b"arriendo" not in destino.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(destino).execute("SELECT * FROM transactions").fetchall()


# ── Enumeración de cuentas ────────────────────────────────────────────────────

def test_PF_SEG_09_login_sin_cuenta_tambien_verifica_bcrypt(client, monkeypatch):
    llamadas = []
    original = bcrypt.checkpw
    monkeypatch.setattr(bcrypt, "checkpw", lambda *a: llamadas.append(1) or original(*a))
    r = login(client, "nadie@finsmart.co", "OtraClave999")
    assert r.status_code == 401
    assert len(llamadas) == 1  # mismo trabajo que con una cuenta real: el tiempo no delata el correo


def test_PF_SEG_10_registro_duplicado_tambien_calcula_el_hash(client, monkeypatch):
    registrar(client, "ana@finsmart.co")
    llamadas = []
    original = auth_router.get_password_hash
    monkeypatch.setattr(auth_router, "get_password_hash", lambda c: llamadas.append(1) or original(c))
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "x12345678", "full_name": "Ana 2"})
    assert r.status_code == 400
    assert len(llamadas) == 1


def test_PF_SEG_11_agregar_miembros_tiene_tope_por_usuario(client, usuario, monkeypatch):
    monkeypatch.setattr(limitador_miembros, "max_intentos", 3)
    grupo = client.post("/shared/groups", json={"name": "Casa"}, headers=usuario).json()
    for i in range(3):
        r = client.post(f"/shared/groups/{grupo['id']}/members",
                        json={"name": f"Persona {i}", "email": f"p{i}@correo-prueba.co"}, headers=usuario)
        assert r.status_code == 201
    r = client.post(f"/shared/groups/{grupo['id']}/members",
                    json={"name": "Persona 4", "email": "p4@correo-prueba.co"}, headers=usuario)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


# ── Manejo de errores y configuración ─────────────────────────────────────────

def test_PF_SEG_12_error_interno_no_expone_detalles(usuario, monkeypatch):
    def falla(*_a, **_k):
        raise RuntimeError("SELECT hashed_password FROM users -- C:/ruta/interna")
    monkeypatch.setattr(recurring_router, "detect_patterns", falla)
    with TestClient(app, raise_server_exceptions=False) as c:
        ajeno = c.get("/recurring/patterns", headers={**usuario, "Origin": "https://sitio-ajeno.co"})
        propio = c.get("/recurring/patterns", headers={**usuario, "Origin": "http://localhost:3000"})
    assert ajeno.status_code == 500
    assert "SELECT" not in ajeno.text and "ruta" not in ajeno.text
    assert "access-control-allow-origin" not in ajeno.headers
    assert propio.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_PU_SEG_13_sin_secret_key_valida_se_usa_una_clave_aleatoria():
    backend = Path(__file__).resolve().parent.parent
    entorno = {**os.environ, "SECRET_KEY": "corta"}
    codigo = "import security; print(security.SECRET_KEY)"
    claves = [
        subprocess.run([sys.executable, "-c", codigo], cwd=backend, env=entorno,
                       capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
        for _ in range(2)
    ]
    assert all(len(c) >= 32 for c in claves)
    assert claves[0] != claves[1]
    assert "change-this-secret-key" not in claves[0]
