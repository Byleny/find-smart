"""RF-02 (metas de ahorro)."""
from datetime import date, timedelta

import pytest


def crear_meta(client, headers, objetivo=500000):
    r = client.post("/goals", json={"name": "Fondo de emergencia", "target_amount": objetivo,
                                    "deadline": (date.today() + timedelta(days=180)).isoformat()}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_PF_AHO_01_crear_meta_inicia_en_cero(client, usuario):
    meta_id = crear_meta(client, usuario)
    meta = next(g for g in client.get("/goals", headers=usuario).json() if g["id"] == meta_id)
    assert meta["current_amount"] == 0


def test_PF_AHO_02_abono_actualiza_el_progreso(client, usuario):
    meta_id = crear_meta(client, usuario, 500000)
    r = client.post(f"/goals/{meta_id}/contribute", json={"amount": 100000}, headers=usuario)
    assert r.status_code == 201
    meta = next(g for g in client.get("/goals", headers=usuario).json() if g["id"] == meta_id)
    assert meta["current_amount"] == 100000
    assert meta["current_amount"] / meta["target_amount"] == pytest.approx(0.20)


def test_PF_AHO_03_abonos_sucesivos_se_acumulan_y_quedan_en_el_historial(client, usuario):
    meta_id = crear_meta(client, usuario)
    for monto in (100000, 50000, 25000):
        client.post(f"/goals/{meta_id}/contribute", json={"amount": monto}, headers=usuario)
    abonos = client.get(f"/goals/{meta_id}/contributions", headers=usuario).json()
    meta = next(g for g in client.get("/goals", headers=usuario).json() if g["id"] == meta_id)
    assert len(abonos) == 3
    assert meta["current_amount"] == 175000


def test_PF_AHO_04_no_se_puede_abonar_a_la_meta_de_otro_usuario(client, usuario, otro_usuario):
    meta_id = crear_meta(client, usuario)
    r = client.post(f"/goals/{meta_id}/contribute", json={"amount": 1000}, headers=otro_usuario)
    assert r.status_code == 404


def test_PF_AHO_05_abono_negativo_es_rechazado(client, usuario):
    meta_id = crear_meta(client, usuario)
    r = client.post(f"/goals/{meta_id}/contribute", json={"amount": -50000}, headers=usuario)
    assert r.status_code == 422
