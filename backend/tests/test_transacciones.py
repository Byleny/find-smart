"""RF-01 (registro de gastos), RNF-02 (aislamiento entre usuarios) y retroalimentación del clasificador."""
from datetime import date

import pytest

from conftest import gasto, historial_entrenable
import services.ml_service as ml_service


def test_PF_GAS_01_registrar_gasto_aparece_en_listado(client, usuario):
    r = gasto(client, usuario, "Mercado", 38000, "Alimentación")
    assert r.status_code == 201
    listado = client.get("/transactions", headers=usuario).json()
    assert [t["description"] for t in listado] == ["Mercado"]


def test_PF_GAS_02_resumen_del_mes_refleja_el_gasto(client, usuario):
    gasto(client, usuario, "Mercado", 38000, "Alimentación")
    gasto(client, usuario, "Salario", 2000000, "Salario", tipo="ingreso")
    resumen = client.get("/transactions/summary", headers=usuario).json()
    assert resumen["total_expenses"] == 38000
    assert resumen["total_income"] == 2000000
    assert resumen["balance"] == 2000000 - 38000
    assert {c["category"]: c["amount"] for c in resumen["by_category"]} == {"Alimentación": 38000}


def test_PF_GAS_03_campos_obligatorios_faltantes_son_rechazados(client, usuario):
    r = client.post("/transactions", json={"description": "Sin monto", "category": "X", "type": "gasto"}, headers=usuario)
    assert r.status_code == 422


def test_PF_GAS_04_fecha_invalida_es_rechazada(client, usuario):
    r = client.post("/transactions", json={"description": "Mercado", "amount": 1000, "category": "Alimentación",
                                           "type": "gasto", "date": "2026-13-45"}, headers=usuario)
    assert r.status_code == 422


def test_PF_GAS_05_monto_negativo_es_rechazado(client, usuario):
    r = gasto(client, usuario, monto=-38000)
    assert r.status_code == 422


def test_PF_GAS_06_tipo_de_transaccion_invalido_es_rechazado(client, usuario):
    r = gasto(client, usuario, tipo="otro")
    assert r.status_code == 422


def test_PF_GAS_07_idor_lectura_un_usuario_no_ve_gastos_ajenos(client, usuario, otro_usuario):
    gasto(client, usuario, "Gasto privado de A", 50000)
    assert client.get("/transactions", headers=otro_usuario).json() == []
    resumen_b = client.get("/transactions/summary", headers=otro_usuario).json()
    assert resumen_b["total_expenses"] == 0


def test_PF_GAS_08_idor_escritura_un_usuario_no_modifica_ni_elimina_gastos_ajenos(client, usuario, otro_usuario):
    tx_id = gasto(client, usuario, "Gasto de A", 50000).json()["id"]
    editar = client.put(f"/transactions/{tx_id}", json={"amount": 1}, headers=otro_usuario)
    borrar = client.delete(f"/transactions/{tx_id}", headers=otro_usuario)
    assert editar.status_code == 404
    assert borrar.status_code == 404
    propio = client.get("/transactions", headers=usuario).json()
    assert propio[0]["amount"] == 50000


def test_PF_GAS_09_corregir_categoria_persiste_y_reentrena_el_clasificador(client, usuario):
    historial_entrenable(client, usuario)
    tx_id = client.get("/transactions", headers=usuario).json()[0]["id"]
    user_id = client.get("/auth/me", headers=usuario).json()["id"]
    modelo = ml_service._cat_path(user_id)
    modelo.unlink(missing_ok=True)

    r = client.put(f"/transactions/{tx_id}", json={"category": "Entretenimiento"}, headers=usuario)

    assert r.status_code == 200
    assert r.json()["category"] == "Entretenimiento"
    assert modelo.exists(), "la edición debe disparar el reentrenamiento en segundo plano"


def test_PF_GAS_10_sugerencia_de_categoria_es_editable_y_no_se_guarda_sola(client, usuario):
    historial_entrenable(client, usuario)
    antes = len(client.get("/transactions", headers=usuario).json())
    sugerencia = client.get("/transactions/ml/suggest", params={"description": "uber al trabajo"}, headers=usuario).json()
    assert sugerencia["category"] == "Transporte"
    assert 0 <= sugerencia["confidence"] <= 1
    assert len(client.get("/transactions", headers=usuario).json()) == antes
