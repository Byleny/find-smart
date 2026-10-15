"""RF-08: presupuestos por categoría con alertas al acercarse o superar el límite."""
from datetime import date

import routers.transactions as transacciones
from conftest import gasto


def crear_presupuesto(client, headers, categoria="Alimentación", limite=100000):
    return client.post("/budgets", json={"category": categoria, "limit_amount": limite}, headers=headers)


def test_PF_PRE_01_crear_presupuesto(client, usuario):
    r = crear_presupuesto(client, usuario)
    assert r.status_code == 201
    assert r.json()["spent_amount"] == 0


def test_PF_PRE_02_el_gasto_del_mes_se_descuenta_del_presupuesto(client, usuario):
    crear_presupuesto(client, usuario, "Alimentación", 100000)
    gasto(client, usuario, "Mercado", 30000, "Alimentación")
    gasto(client, usuario, "Uber", 15000, "Transporte")
    presupuesto = client.get("/budgets", headers=usuario).json()[0]
    assert presupuesto["spent_amount"] == 30000


def test_PF_PRE_03_alerta_al_cruzar_el_90_y_el_100_por_ciento(client, usuario, monkeypatch):
    alertas = []
    monkeypatch.setattr(transacciones, "send_budget_alert_email",
                        lambda email, cat, gastado, limite, superado: alertas.append((gastado, superado)))
    crear_presupuesto(client, usuario, "Alimentación", 100000)
    gasto(client, usuario, "Mercado", 50000, "Alimentación")   # 50 %: sin alerta
    gasto(client, usuario, "Mercado", 42000, "Alimentación")   # 92 %: alerta de cercanía
    gasto(client, usuario, "Mercado", 3000, "Alimentación")    # 95 %: ya alertado, sin repetir
    gasto(client, usuario, "Mercado", 10000, "Alimentación")   # 105 %: alerta de exceso
    assert alertas == [(92000, False), (105000, True)]


def test_PF_PRE_04_limite_no_positivo_es_rechazado(client, usuario):
    assert crear_presupuesto(client, usuario, limite=0).status_code == 422
    assert crear_presupuesto(client, usuario, limite=-5000).status_code == 422


def test_PF_PRE_05_no_se_modifica_el_presupuesto_de_otro_usuario(client, usuario, otro_usuario):
    presupuesto_id = crear_presupuesto(client, usuario).json()["id"]
    r = client.put(f"/budgets/{presupuesto_id}", json={"limit_amount": 1}, headers=otro_usuario)
    assert r.status_code == 404
    assert client.get("/budgets", headers=usuario).json()[0]["limit_amount"] == 100000
