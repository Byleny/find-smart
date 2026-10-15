"""RF-04, RF-05 y RF-06: patrones recurrentes, registro de contratos y consulta de facturas.

La consulta en vivo a GDO no se ejecuta aquí porque depende de la disponibilidad de un
portal externo; se verifica de forma manual (Tabla de pruebas funcionales del documento).
"""
from datetime import date, timedelta

from conftest import gasto
from services.scraper_service import PROVIDER_REGISTRY, ManualPortalScraper, GDOScraper

REDIRECCION = ["emcali", "claro", "celsia", "movistar", "tigo"]


def contrato(client, headers, proveedor="gdo", referencia="123456"):
    return client.post("/invoices/contracts", json={
        "name": f"Servicio {proveedor}", "provider": proveedor, "account_reference": referencia,
        "category": "Servicios", "estimated_amount": 50000, "billing_day": 10,
    }, headers=headers)


def test_PF_SRV_01_registrar_contrato_de_proveedor_del_catalogo(client, usuario):
    r = contrato(client, usuario, "gdo")
    assert r.status_code == 201
    assert r.json()["provider"] == "gdo"


def test_PF_SRV_02_proveedor_sin_consulta_automatica_es_rechazado(client, usuario):
    r = contrato(client, usuario, "netflix")
    assert r.status_code == 400


def test_PF_SRV_03_contrato_duplicado_es_rechazado(client, usuario):
    contrato(client, usuario, "gdo", "777")
    assert contrato(client, usuario, "gdo", "777").status_code == 400


def test_PF_SRV_04_proveedores_sin_automatizacion_redirigen_al_portal_oficial():
    for proveedor in REDIRECCION:
        scraper = PROVIDER_REGISTRY[proveedor]
        assert isinstance(scraper, ManualPortalScraper), proveedor
        resultado = scraper.fetch_invoice("123")
        assert resultado.portal_blocked is True
        assert resultado.payment_url.startswith("https://")


def test_PF_SRV_05_gdo_es_el_unico_proveedor_con_consulta_en_vivo():
    assert isinstance(PROVIDER_REGISTRY["gdo"], GDOScraper)


def test_PF_SRV_06_consulta_de_factura_con_redireccion_de_extremo_a_extremo(client, usuario):
    contrato_id = contrato(client, usuario, "tigo", "3001234567").json()["id"]
    r = client.post(f"/invoices/contracts/{contrato_id}/fetch", headers=usuario)
    assert r.status_code == 200
    assert r.json()["portal_blocked"] is True
    assert "tigo" in r.json()["payment_url"]


def test_PF_SRV_07_no_se_consulta_el_contrato_de_otro_usuario(client, usuario, otro_usuario):
    contrato_id = contrato(client, usuario, "tigo").json()["id"]
    assert client.post(f"/invoices/contracts/{contrato_id}/fetch", headers=otro_usuario).status_code == 404


def test_PF_SRV_08_patrones_recurrentes_desde_el_historial_registrado(client, usuario):
    inicio = date.today() - timedelta(days=90)
    for k in range(4):
        gasto(client, usuario, "Netflix", 38900, "Entretenimiento", inicio + timedelta(days=30 * k))
    gasto(client, usuario, "Cine", 25000, "Entretenimiento", inicio + timedelta(days=5))
    patrones = client.get("/recurring/patterns", headers=usuario).json()
    assert len(patrones) == 1
    assert patrones[0]["service_name"] == "netflix"
    assert patrones[0]["confidence"] == 1.0
