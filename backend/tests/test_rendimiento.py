"""RNF-01: tiempo de respuesta de los endpoints habituales con un historial de 208 transacciones.

Las mediciones se hacen dentro del proceso con el cliente de pruebas de FastAPI, por lo que
no incluyen latencia de red. En las solicitudes POST el cliente espera además a que terminen
las tareas en segundo plano (reentrenamiento), algo que el servidor real no hace antes de
responder; su tiempo es, por lo tanto, una cota superior.
"""
import json
import os
import random
import statistics
import time
from datetime import date, timedelta

from database import SessionLocal
from models import Transaction, User

N = 30
LIMITE_SEGUNDOS = 2.0


def sembrar_historial(email):
    random.seed(42)
    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    categorias = {"Alimentación": ["mercado exito", "mercado d1", "domicilio comida"],
                  "Transporte": ["uber viaje", "taxi centro", "recarga mio"],
                  "Servicios": ["gas gdo", "acueducto emcali", "claro internet hogar"],
                  "Entretenimiento": ["netflix", "spotify", "cine colombia"],
                  "Salud": ["drogueria", "consulta medica", "fisioterapia"],
                  "Vivienda": ["arriendo apartamento", "administracion", "detergente"]}
    hoy = date.today()
    for i in range(208):
        cat = random.choice(list(categorias))
        db.add(Transaction(user_id=user_id, description=random.choice(categorias[cat]),
                           amount=random.randint(5000, 200000), category=cat, type="gasto",
                           date=hoy - timedelta(days=random.randint(0, 120))))
    db.commit()
    db.close()


def medir(fn):
    tiempos = []
    for _ in range(N):
        t0 = time.perf_counter()
        r = fn()
        tiempos.append(time.perf_counter() - t0)
        assert r.status_code in (200, 201), r.text
    tiempos.sort()
    return {"media_ms": round(statistics.mean(tiempos) * 1000, 1),
            "p95_ms": round(tiempos[int(0.95 * N) - 1] * 1000, 1),
            "max_ms": round(tiempos[-1] * 1000, 1)}


def test_RNF_01_tiempos_de_respuesta_con_208_transacciones(client):
    email = "rendimiento@finsmart.co"
    r = client.post("/auth/register", json={"acepta_politica": True, "email": email, "password": "ClaveSegura123", "full_name": "Perf"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    sembrar_historial(email)

    resultados = {
        "GET /transactions/summary": medir(lambda: client.get("/transactions/summary", headers=headers)),
        "GET /transactions": medir(lambda: client.get("/transactions", headers=headers)),
        "GET /recurring/patterns": medir(lambda: client.get("/recurring/patterns", headers=headers)),
        "GET /transactions/ml/suggest": medir(lambda: client.get("/transactions/ml/suggest", params={"description": "uber al centro"}, headers=headers)),
        "POST /transactions (incluye reentrenamiento)": medir(lambda: client.post("/transactions", json={
            "description": "mercado", "amount": 45000, "category": "Alimentación", "type": "gasto",
            "date": date.today().isoformat()}, headers=headers)),
    }

    salida = os.environ.get("FINSMART_PERF_OUT")
    if salida:
        with open(salida, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)

    for endpoint, m in resultados.items():
        assert m["p95_ms"] / 1000 < LIMITE_SEGUNDOS, endpoint
