"""RF-07 (registro y autenticación) y RNF-02 (seguridad)."""
from datetime import timedelta

from conftest import registrar, gasto
from database import SessionLocal
from models import User, Transaction
from politica import POLITICA_VERSION
from routers.auth import REGISTRO_NO_COMPLETADO
from security import create_access_token


def login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_PF_AUT_01_registro_exitoso_retorna_token(client):
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "ClaveSegura123", "full_name": "Ana"})
    assert r.status_code == 201
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_PF_AUT_02_login_con_credenciales_correctas(client):
    registrar(client, "ana@finsmart.co", "ClaveSegura123")
    r = login(client, "ana@finsmart.co", "ClaveSegura123")
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_PF_AUT_03_login_con_contrasena_incorrecta_es_rechazado(client):
    registrar(client, "ana@finsmart.co", "ClaveSegura123")
    r = login(client, "ana@finsmart.co", "OtraClave999")
    assert r.status_code == 401


def test_PF_AUT_04_login_no_distingue_correo_inexistente_de_contrasena_incorrecta(client):
    registrar(client, "ana@finsmart.co", "ClaveSegura123")
    mala_clave = login(client, "ana@finsmart.co", "OtraClave999")
    sin_cuenta = login(client, "nadie@finsmart.co", "OtraClave999")
    assert mala_clave.status_code == sin_cuenta.status_code == 401
    assert mala_clave.json()["detail"] == sin_cuenta.json()["detail"]


def test_PF_AUT_05_registro_con_correo_duplicado_es_rechazado(client):
    registrar(client, "ana@finsmart.co")
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "x12345678", "full_name": "Ana 2"})
    assert r.status_code == 400


def test_PF_AUT_06_registro_duplicado_no_revela_que_el_correo_existe(client):
    registrar(client, "ana@finsmart.co")
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "x12345678", "full_name": "Ana 2"})
    detalle = r.json()["detail"]
    assert detalle == REGISTRO_NO_COMPLETADO
    assert not any(pista in detalle.lower() for pista in ("ya existe", "registrado", "already", "ana@finsmart.co"))


def test_PF_AUT_07_registro_con_correo_invalido_es_rechazado(client):
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "no-es-un-correo", "password": "ClaveSegura123", "full_name": "Ana"})
    assert r.status_code == 422


def test_PF_AUT_08_ruta_protegida_sin_token_retorna_401(client):
    assert client.get("/transactions").status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_PF_AUT_09_token_con_firma_alterada_retorna_401(client, usuario):
    token = usuario["Authorization"].split()[1]
    alterado = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {alterado}"})
    assert r.status_code == 401


def test_PF_AUT_10_token_vencido_retorna_401(client):
    _, email = registrar(client)
    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    db.close()
    vencido = create_access_token({"sub": str(user_id)}, expires_delta=timedelta(seconds=-1))
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {vencido}"})
    assert r.status_code == 401


def test_PF_AUT_11_contrasena_se_almacena_con_hash_bcrypt(client):
    registrar(client, "ana@finsmart.co", "ClaveSegura123")
    db = SessionLocal()
    user = db.query(User).filter(User.email == "ana@finsmart.co").first()
    db.close()
    assert user.hashed_password != "ClaveSegura123"
    assert user.hashed_password.startswith("$2")


def test_PF_AUT_12_eliminar_cuenta_exige_contrasena_correcta(client, usuario):
    r = client.request("DELETE", "/auth/me", json={"password": "Incorrecta1"}, headers=usuario)
    assert r.status_code == 401


def test_PF_AUT_13_eliminar_cuenta_borra_sus_datos(client):
    headers, email = registrar(client, password="ClaveSegura123")
    gasto(client, headers)
    r = client.request("DELETE", "/auth/me", json={"password": "ClaveSegura123"}, headers=headers)
    assert r.status_code == 204
    assert login(client, email, "ClaveSegura123").status_code == 401
    db = SessionLocal()
    assert db.query(User).filter(User.email == email).first() is None
    assert db.query(Transaction).count() == 0
    db.close()


def test_PF_AUT_14_contrasena_de_menos_de_8_caracteres_es_rechazada(client):
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "Corta12", "full_name": "Ana"})
    assert r.status_code == 422
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "Justa123", "full_name": "Ana"})
    assert r.status_code == 201


def test_PF_AUT_15_contrasena_de_mas_de_72_caracteres_es_rechazada(client):
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "ana@finsmart.co", "password": "a" * 73, "full_name": "Ana"})
    assert r.status_code == 422


def test_PF_AUT_16_el_mismo_correo_con_otras_mayusculas_no_crea_otra_cuenta(client):
    registrar(client, "ana@finsmart.co", "ClaveSegura123")
    r = client.post("/auth/register", json={"acepta_politica": True, "email": "Ana@Finsmart.co", "password": "OtraClave999", "full_name": "Ana 2"})
    assert r.status_code == 400
    assert r.json()["detail"] == REGISTRO_NO_COMPLETADO
    assert login(client, "ANA@finsmart.co", "ClaveSegura123").status_code == 200


def test_PF_AUT_17_registro_sin_aceptar_la_politica_es_rechazado(client):
    base = {"email": "ana@finsmart.co", "password": "ClaveSegura123", "full_name": "Ana"}
    assert client.post("/auth/register", json=base).status_code == 422
    assert client.post("/auth/register", json={**base, "acepta_politica": False}).status_code == 422
    r = client.post("/auth/register", json={**base, "acepta_politica": True})
    assert r.status_code == 201
    yo = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert yo["politica_pendiente"] is False
    assert yo["politica_version"] == POLITICA_VERSION
    assert yo["politica_aceptada_en"]


def test_PF_AUT_18_cuenta_sin_politica_aceptada_no_accede_a_sus_datos(client):
    headers, email = registrar(client)
    db = SessionLocal()
    db.query(User).filter(User.email == email).update({"politica_version": None, "politica_aceptada_en": None})
    db.commit()
    db.close()
    for ruta in ("/transactions", "/budgets", "/goals", "/shared/groups", "/recurring/patterns", "/notifications"):
        assert client.get(ruta, headers=headers).status_code == 403, ruta
    assert client.get("/auth/me", headers=headers).json()["politica_pendiente"] is True
    aceptada = client.post("/auth/politica/aceptar", headers=headers)
    assert aceptada.status_code == 200
    assert aceptada.json()["politica_pendiente"] is False
    assert client.get("/transactions", headers=headers).status_code == 200


def test_PF_AUT_19_la_politica_es_publica_e_identifica_al_responsable(client, monkeypatch):
    monkeypatch.setenv("POLITICA_CORREO", "datos@correo-prueba.co")
    r = client.get("/auth/politica")
    assert r.status_code == 200
    datos = r.json()
    assert datos["version"] == POLITICA_VERSION
    assert datos["responsable"]
    assert datos["correo"] == "datos@correo-prueba.co"
