"""RF-09: notificaciones de invitación a grupos y su aceptación o rechazo."""
from conftest import registrar


def invitar(client, creador, email_invitado):
    grupo = client.post("/shared/groups", json={"name": "Apartamento"}, headers=creador).json()
    client.post(f"/shared/groups/{grupo['id']}/members",
                json={"name": "Invitado", "email": email_invitado}, headers=creador)
    return grupo["id"]


def test_PF_NOT_01_la_invitacion_llega_como_notificacion_pendiente(client, usuario):
    headers_b, email_b = registrar(client)
    invitar(client, usuario, email_b)
    notificaciones = client.get("/notifications", headers=headers_b).json()
    assert len(notificaciones) == 1
    assert notificaciones[0]["type"] == "group_invite"
    assert notificaciones[0]["status"] == "pending"


def test_PF_NOT_02_aceptar_la_invitacion_agrega_al_integrante(client, usuario):
    headers_b, email_b = registrar(client)
    grupo_id = invitar(client, usuario, email_b)
    notif = client.get("/notifications", headers=headers_b).json()[0]
    assert client.post(f"/notifications/{notif['id']}/accept", headers=headers_b).status_code == 200
    miembros = client.get(f"/shared/groups/{grupo_id}", headers=usuario).json()["members"]
    assert any(m["email"] == email_b and m["user_id"] is not None for m in miembros)


def test_PF_NOT_03_rechazar_la_invitacion_no_agrega_al_integrante(client, usuario):
    headers_b, email_b = registrar(client)
    grupo_id = invitar(client, usuario, email_b)
    notif = client.get("/notifications", headers=headers_b).json()[0]
    assert client.post(f"/notifications/{notif['id']}/reject", headers=headers_b).status_code == 200
    assert client.get(f"/shared/groups/{grupo_id}", headers=headers_b).status_code == 403


def test_PF_NOT_04_no_se_puede_resolver_la_notificacion_de_otro_usuario(client, usuario, otro_usuario):
    headers_b, email_b = registrar(client)
    invitar(client, usuario, email_b)
    notif = client.get("/notifications", headers=headers_b).json()[0]
    assert client.post(f"/notifications/{notif['id']}/accept", headers=otro_usuario).status_code == 404


def test_PF_NOT_05_una_notificacion_resuelta_no_se_resuelve_dos_veces(client, usuario):
    headers_b, email_b = registrar(client)
    invitar(client, usuario, email_b)
    notif = client.get("/notifications", headers=headers_b).json()[0]
    client.post(f"/notifications/{notif['id']}/reject", headers=headers_b)
    assert client.post(f"/notifications/{notif['id']}/accept", headers=headers_b).status_code == 400
