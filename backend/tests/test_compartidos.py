"""RF-03 (gastos compartidos) y control del rol de creador (amenaza E del análisis STRIDE)."""
from datetime import date

from conftest import registrar


def crear_grupo(client, headers, nombre="Apartamento"):
    r = client.post("/shared/groups", json={"name": nombre}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def agregar_integrante(client, headers, grupo_id, nombre="Integrante B", email="b@correo-prueba.co"):
    return client.post(f"/shared/groups/{grupo_id}/members", json={"name": nombre, "email": email}, headers=headers)


def test_PF_COM_01_el_creador_queda_como_primer_integrante(client, usuario):
    grupo = crear_grupo(client, usuario)
    assert len(grupo["members"]) == 1
    assert grupo["members"][0]["user_id"] is not None


def test_PF_COM_02_integrante_sin_cuenta_se_agrega_directamente(client, usuario):
    grupo = crear_grupo(client, usuario)
    r = agregar_integrante(client, usuario, grupo["id"])
    assert r.status_code == 201
    assert r.json()["status"] == "added"


def test_PF_COM_03_integrante_con_cuenta_recibe_invitacion(client, usuario):
    _, email_b = registrar(client)
    grupo = crear_grupo(client, usuario)
    r = agregar_integrante(client, usuario, grupo["id"], email=email_b)
    assert r.status_code == 201
    assert r.json()["status"] == "invited"


def test_PF_COM_04_gasto_se_reparte_y_calcula_la_deuda(client, usuario):
    grupo = crear_grupo(client, usuario)
    agregar_integrante(client, usuario, grupo["id"])
    detalle = client.get(f"/shared/groups/{grupo['id']}", headers=usuario).json()
    a = next(m for m in detalle["members"] if m["user_id"] is not None)
    b = next(m for m in detalle["members"] if m["user_id"] is None)

    r = client.post(f"/shared/groups/{grupo['id']}/expenses",
                    json={"description": "Mercado", "amount": 90000, "paid_by_id": a["id"], "date": date.today().isoformat()},
                    headers=usuario)
    assert r.status_code == 201
    repartos = {s["member_id"]: s for s in r.json()["splits"]}
    assert repartos[a["id"]]["amount"] == repartos[b["id"]]["amount"] == 45000
    assert repartos[a["id"]]["is_settled"] is True
    assert repartos[b["id"]]["is_settled"] is False

    saldos = {s["member_id"]: s for s in client.get(f"/shared/groups/{grupo['id']}/balances", headers=usuario).json()}
    assert saldos[b["id"]]["net_balance"] == -45000
    assert saldos[a["id"]]["net_balance"] == 45000


def test_PF_COM_05_usuario_ajeno_no_accede_al_grupo(client, usuario, otro_usuario):
    grupo = crear_grupo(client, usuario)
    assert client.get(f"/shared/groups/{grupo['id']}", headers=otro_usuario).status_code == 403
    assert client.get(f"/shared/groups/{grupo['id']}/balances", headers=otro_usuario).status_code == 403


def test_PF_COM_06_integrante_que_no_es_creador_no_administra_integrantes(client, usuario):
    headers_b, email_b = registrar(client)
    grupo = crear_grupo(client, usuario)
    agregar_integrante(client, usuario, grupo["id"], email=email_b)
    invitacion = client.get("/notifications", headers=headers_b).json()[0]
    assert client.post(f"/notifications/{invitacion['id']}/accept", headers=headers_b).status_code == 200
    assert client.get(f"/shared/groups/{grupo['id']}", headers=headers_b).status_code == 200

    r = agregar_integrante(client, headers_b, grupo["id"], nombre="Intruso", email="c@correo-prueba.co")
    assert r.status_code == 403


def test_PF_COM_07_correo_de_integrante_invalido_es_rechazado(client, usuario):
    grupo = crear_grupo(client, usuario)
    assert agregar_integrante(client, usuario, grupo["id"], email="no-es-correo").status_code == 422
