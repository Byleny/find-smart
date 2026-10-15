"""Pruebas unitarias del módulo de IA: Regresión Logística, Isolation Forest y DBSCAN (RF-04)."""
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

import services.ml_service as ml
from services.ai_service import detect_patterns, predict_next_payment

BASE = date(2026, 1, 5)
_id = iter(range(1, 100000))


def tx(descripcion, monto=10000, categoria="Otros", fecha=BASE, tipo="gasto"):
    return SimpleNamespace(id=next(_id), description=descripcion, amount=float(monto),
                           category=categoria, date=fecha, type=tipo)


def historial_clasificable():
    datos = [("uber viaje", "Transporte"), ("uber aeropuerto", "Transporte"), ("taxi centro", "Transporte"),
             ("uber noche", "Transporte"), ("netflix plan", "Entretenimiento"), ("cine colombia", "Entretenimiento"),
             ("spotify premium", "Entretenimiento"), ("netflix mensual", "Entretenimiento"),
             ("mercado exito", "Alimentación"), ("mercado d1", "Alimentación"), ("domicilio comida", "Alimentación"),
             ("mercado mensual", "Alimentación")]
    return [tx(d, 20000, c, BASE + timedelta(days=i)) for i, (d, c) in enumerate(datos)]


# ── Ingeniería de características ────────────────────────────────────────────

def test_PU_IA_01_isolation_forest_usa_cuatro_caracteristicas():
    t = tx("mercado", 100000, "Alimentación", date(2026, 3, 17))
    X, ids = ml._build_features([t, tx("mercado", 50000, "Alimentación")])
    assert X.shape == (2, 4)
    assert X[0][0] == np.log1p(100000)
    assert X[0][2] == 17 and X[0][3] == 3
    assert ids[0] == t.id


# ── Regresión Logística ───────────────────────────────────────────────────────

def test_PU_IA_02_clasificador_no_se_entrena_con_menos_de_diez_gastos():
    assert ml.train_category_model(901, historial_clasificable()[:9]) is None


def test_PU_IA_03_clasificador_no_se_entrena_con_una_sola_categoria_valida():
    solo_transporte = [tx(f"uber viaje {i}", 15000, "Transporte") for i in range(12)]
    assert ml.train_category_model(902, solo_transporte) is None


def test_PU_IA_04_clasificador_sugiere_categoria_con_confianza_y_alternativas():
    assert ml.train_category_model(903, historial_clasificable()) is not None
    pred = ml.predict_category(903, "uber al trabajo")
    assert pred["category"] == "Transporte"
    assert 0 < pred["confidence"] <= 1
    assert len(pred["alternatives"]) == 2
    assert pred["confidence"] >= max(a["confidence"] for a in pred["alternatives"])


def test_PU_IA_05_sin_modelo_entrenado_no_hay_sugerencia():
    assert ml.predict_category(904, "uber") is None


# ── Isolation Forest ──────────────────────────────────────────────────────────

def test_PU_IA_06_isolation_forest_marca_un_gasto_extremo_como_anomalia():
    rng = np.random.default_rng(7)
    normales = [tx("mercado", float(rng.normal(80000, 8000)), "Alimentación", BASE + timedelta(days=i))
                for i in range(40)]
    extremo = tx("mercado", 960000, "Alimentación", BASE + timedelta(days=20))
    historial = normales + [extremo]

    assert ml.train_anomaly_model(905, historial) is True
    resultado = {r["transaction_id"]: r for r in ml.score_anomalies(905, historial)}

    assert resultado[extremo.id]["is_anomaly"] is True
    assert resultado[extremo.id]["anomaly_score"] == min(r["anomaly_score"] for r in resultado.values())
    assert sum(r["is_anomaly"] for r in resultado.values()) <= 2


def test_PU_IA_07_isolation_forest_no_se_entrena_con_menos_de_diez_gastos():
    assert ml.train_anomaly_model(906, [tx("mercado", 1000 * i) for i in range(1, 10)]) is False


# ── DBSCAN: patrones recurrentes ──────────────────────────────────────────────

def mensual(descripcion, n=4, cada=30, inicio=BASE):
    return [tx(descripcion, 38900, "Entretenimiento", inicio + timedelta(days=cada * k)) for k in range(n)]


def test_PU_IA_08_pago_mensual_exacto_tiene_confianza_uno():
    patrones = detect_patterns(mensual("netflix", 4, 30))
    assert len(patrones) == 1
    p = patrones[0]
    assert p.confidence == 1.0
    assert p.occurrences == 4
    assert p.next_predicted_date == BASE + timedelta(days=120)


def test_PU_IA_09_intervalos_irregulares_reducen_la_confianza():
    fechas = [BASE, BASE + timedelta(days=20), BASE + timedelta(days=60), BASE + timedelta(days=90)]
    intervalos = np.array([20, 40, 30], dtype=float)
    esperada = round(1 - intervalos.std() / intervalos.mean(), 3)
    patrones = detect_patterns([tx("gimnasio", 90000, "Salud", f) for f in fechas])
    assert patrones[0].confidence == esperada
    assert patrones[0].confidence < 1.0


def test_PU_IA_10_variantes_de_escritura_del_mismo_comercio_se_agrupan():
    # Historial realista: las variantes conviven con otros comercios, como en el uso real.
    netflix = ["Netflix", "NETFLIX.COM", "Netflix", "NETFLIX.COM"]
    claro = ["Claro Internet Hogar", "Claro Hogar", "Claro Internet Hogar", "Claro Hogar"]
    historial = [tx(d, 38900, "Entretenimiento", BASE + timedelta(days=30 * k)) for k, d in enumerate(netflix)]
    historial += [tx(d, 79900, "Servicios", BASE + timedelta(days=30 * k + 3)) for k, d in enumerate(claro)]
    historial += [tx("Mercado Exito", 120000, "Alimentación", BASE + timedelta(days=11))]
    patrones = detect_patterns(historial)
    assert len(patrones) == 2
    assert sorted(p.occurrences for p in patrones) == [4, 4]


def test_PU_IA_11_menos_de_tres_ocurrencias_no_es_un_patron():
    assert detect_patterns(mensual("netflix", 2) + [tx("arriendo"), tx("cine")]) == []


def test_PU_IA_12_intervalo_medio_menor_a_siete_dias_se_descarta():
    assert detect_patterns(mensual("cafe", 6, cada=1)) == []


def test_PU_IA_13_comercios_distintos_forman_patrones_separados():
    historial = mensual("netflix", 4) + mensual("arriendo apartamento", 4) + mensual("gas gdo", 4)
    nombres = {p.service_name for p in detect_patterns(historial)}
    assert nombres == {"netflix", "arriendo apartamento", "gas gdo"}


def test_PU_IA_14_proxima_fecha_de_pago_usa_el_intervalo_de_las_facturas():
    servicio = SimpleNamespace(id=1, name="Gas GDO", billing_day=10, estimated_amount=50000, last_fetched_amount=None)
    facturas = [SimpleNamespace(due_date=date(2026, 1, 10)), SimpleNamespace(due_date=date(2026, 2, 9))]
    prediccion = predict_next_payment(servicio, facturas)
    assert prediccion["next_predicted_date"] == "2026-03-11"
