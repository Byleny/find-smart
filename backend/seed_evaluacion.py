"""
Seed evaluacion - FinSmart
==========================
Crea una cuenta de demostracion fresca, pensada para que el profesor
evalue la app manana. Incluye:
  * ~5 meses de transacciones (para tendencias + entrenamiento ML)
  * Categorias de transporte separadas ("Transporte publico" /
    "Transporte privado") para mostrar que las categorias son libres,
    no una lista fija -- se puede dividir cualquier categoria como se
    quiera.
  * Presupuestos por categoria, incluyendo uno para cada tipo de
    transporte por separado.
  * Meta de ahorro con contribuciones.
  * Grupo familiar compartido con un miembro sin cuenta.
  * Modelos ML (categorizacion + anomalias) entrenados al final.

Credenciales:
  evaluacion@finsmart.co  /  demo1234
"""

import random
import sys
sys.stdout.reconfigure(encoding="utf-8")

from datetime import date, timedelta
from database import SessionLocal, engine, Base
from models import (
    User, Transaction, Budget, SavingGoal, SavingContribution,
    SharedGroup, SharedGroupMember, SharedExpense, SharedExpenseSplit,
)
from security import get_password_hash

Base.metadata.create_all(bind=engine)

db = SessionLocal()
today = date.today()
random.seed(7)  # reproducible entre corridas


def ago(days: int) -> date:
    return today - timedelta(days=days)


def month_bounds(n_months_ago: int) -> tuple[date, date]:
    """Rango [inicio, fin] del mes que empezó hace n_months_ago meses completos."""
    m, y = today.month - n_months_ago, today.year
    while m <= 0:
        m += 12
        y -= 1
    start = date(y, m, 1)
    next_m, next_y = (1, y + 1) if m == 12 else (m + 1, y)
    end = date(next_y, next_m, 1) - timedelta(days=1)
    if n_months_ago == 0:
        end = min(end, today)  # el mes actual está incompleto
    return start, end


def date_in_month(n_months_ago: int) -> date:
    start, end = month_bounds(n_months_ago)
    span = max((end - start).days, 0)
    return start + timedelta(days=random.randint(0, span))


# Genera montos por categoría a lo largo de 5 meses (0 = mes actual/parcial,
# 1 = mes pasado completo — el que se usa en "Tendencias" —, 2..4 = los 3
# meses anteriores para el promedio). Cada ítem tiene un monto base y un
# ruido leve mes a mes para que el gasto se vea estable/realista en vez de
# saltos extremos. `story` permite forzar una tendencia real y moderada en
# el mes pasado para una o dos categorías (en vez de que todas suban).
def gen_monthly(category: str, items: list[tuple[str, int]], story: dict[int, float] | None = None):
    story = story or {}
    out = []
    for n_months_ago in range(0, 5):
        factor = story.get(n_months_ago, random.uniform(0.90, 1.10))
        for desc, base_amount in items:
            amount = round(base_amount * factor * random.uniform(0.95, 1.05) / 100) * 100
            out.append((desc, amount, category, date_in_month(n_months_ago)))
    return out


EMAIL = "evaluacion@finsmart.co"
PASSWORD = "demo1234"
FULL_NAME = "Camila Torres"

print("\n-- Usuario --------------------------------------------")
user = db.query(User).filter(User.email == EMAIL).first()
if user:
    print(f"  * Ya existe {EMAIL}, se reutiliza (no se duplican datos)")
else:
    user = User(email=EMAIL, hashed_password=get_password_hash(PASSWORD), full_name=FULL_NAME)
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"  [OK] Usuario creado: {EMAIL} / {PASSWORD}")

# ========================================================
# TRANSACCIONES — 5 meses, transporte separado en 2 categorias
# ========================================================
print("\n-- Transacciones ----------------------------------------")

# Gasto mensual "regular" por categoría — se repite cada uno de los 5 meses
# con ruido leve (±10% por mes, ±5% por ítem) para que el historial se vea
# realista. `story` fuerza una tendencia real y moderada en el mes pasado
# (mes_ago=1, el que usa la pantalla de Tendencias) para un par de
# categorías en vez de que todas suban a la vez.
gastos: list[tuple[str, int, str, date]] = []

gastos += gen_monthly("Alimentación", [
    ("Supermercado Éxito", 42_000),
    ("Mercado La 14", 27_000),
    ("Restaurante El Patio", 23_000),
    ("Domicilio Rappi", 19_000),
    ("Domicilio Rappi", 17_000),
    ("Panadería del barrio", 6_500),
    ("Frutas y verduras", 9_000),
    ("Cafetería oficina", 5_000),
    ("Cafetería oficina", 5_000),
])

gastos += gen_monthly("Transporte público", [
    ("Recarga tarjeta MIO", 8_000),
    ("Recarga tarjeta MIO", 8_000),
    ("Recarga tarjeta MIO", 8_000),
    ("SITP recarga", 6_000),
    ("Bus intermunicipal", 18_000),
], story={1: 0.75})  # el mes pasado bajó ~25% — tendencia real, no ruido

gastos += gen_monthly("Transporte privado", [
    ("Uber", 14_000),
    ("Uber", 13_000),
    ("InDriver", 11_000),
    ("Gasolina vehículo", 85_000),
    ("Parqueadero centro", 5_000),
])

gastos += gen_monthly("Vivienda", [
    ("Arriendo apartamento", 950_000),
    ("Administración", 98_000),
], story={0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0})  # arriendo fijo, sin variación

gastos += gen_monthly("Servicios", [
    ("Claro internet hogar", 79_900),
    ("Acueducto EMCALI", 45_000),
    ("Gas GDO", 29_000),
    ("Energía Enel", 56_000),
    ("Plan celular Claro", 39_900),
])

gastos += gen_monthly("Entretenimiento", [
    ("Netflix", 22_900),
    ("Spotify", 10_900),
    ("Cine Colombia", 20_000),
], story={1: 1.4})  # el mes pasado subió ~40% — tendencia real, no ruido

gastos += gen_monthly("Salud", [
    ("Droguería Cruz Verde", 16_000),
    ("Gimnasio Smart Fit", 65_000),
])

gastos += gen_monthly("Compras", [
    ("Compras varias", 45_000),
])

# Anomalías plantadas para Isolation Forest — puestas a propósito 5-6 meses
# atrás, fuera por completo de las ventanas que usan Tendencias (mes pasado
# + promedio de los 3 anteriores) y Presupuestos (mes actual). Así Isolation
# Forest las sigue viendo en el historial completo, pero no inflan ni el %
# de Tendencias ni el "gastado" del mes actual.
gastos += [
    ("Supermercado Éxito", 480_000, "Alimentación", date_in_month(5)),
    ("Reparación vehículo", 620_000, "Transporte privado", date_in_month(6)),
]

ingresos = [(f"Salario", 3_100_000 + random.randint(-20_000, 20_000), "Salario", date_in_month(n)) for n in range(5)]
ingresos += [
    ("Freelance diseño", 380_000, "Freelance", date_in_month(2)),
    ("Freelance diseño", 420_000, "Freelance", date_in_month(4)),
    ("Venta artículo usado", 150_000, "Ventas", date_in_month(1)),
]

# Reemplaza cualquier dato previo de este usuario (de corridas anteriores de
# este script) en vez de acumularlo — así el arreglo de "Tendencias" aplica
# de verdad y no queda mezclado con datos viejos ya desbalanceados.
deleted = db.query(Transaction).filter(Transaction.user_id == user.id).delete()
db.commit()
if deleted:
    print(f"  * {deleted} transacciones previas eliminadas (se regeneran de cero)")

for desc, amount, cat, tdate in gastos:
    db.add(Transaction(user_id=user.id, description=desc, amount=amount,
                        category=cat, type="gasto", date=tdate))
for desc, amount, cat, tdate in ingresos:
    db.add(Transaction(user_id=user.id, description=desc, amount=amount,
                        category=cat, type="ingreso", date=tdate))

db.commit()
print(f"  [OK] {len(gastos) + len(ingresos)} transacciones agregadas ({len(gastos)} gastos + {len(ingresos)} ingresos)")

# ========================================================
# PRESUPUESTOS — transporte publico y privado por separado
# ========================================================
print("\n-- Presupuestos -----------------------------------------")

budgets_data = [
    ("Alimentación",          250_000),
    ("Transporte público",     55_000),
    ("Transporte privado",    200_000),
    ("Servicios",             280_000),
    ("Entretenimiento",        65_000),
    ("Salud",                 100_000),
    ("Vivienda",             1_100_000),
    ("Compras",                 60_000),
]

for cat, limit in budgets_data:
    existing_budget = db.query(Budget).filter(Budget.user_id == user.id, Budget.category == cat).first()
    if existing_budget:
        existing_budget.limit_amount = limit  # refresca el límite si el script ya se corrió antes
        print(f"  [OK] Presupuesto {cat} actualizado: ${limit:,.0f}")
    else:
        db.add(Budget(user_id=user.id, category=cat, limit_amount=limit, period="monthly"))
        print(f"  [OK] Presupuesto {cat} creado: ${limit:,.0f}")

db.commit()

# ========================================================
# META DE AHORRO
# ========================================================
print("\n-- Meta de ahorro ---------------------------------------")

goal_name = "Vacaciones fin de año"
existing_goal = db.query(SavingGoal).filter(
    SavingGoal.user_id == user.id, SavingGoal.name == goal_name
).first()

if existing_goal:
    print(f"  * Ya existe meta: {goal_name}")
    goal = existing_goal
else:
    contributions = [
        (250_000, "Ahorro mensual", ago(90)),
        (250_000, "Ahorro mensual", ago(60)),
        (300_000, "Ahorro mensual", ago(30)),
        (200_000, "Extra freelance", ago(15)),
    ]
    total = sum(c[0] for c in contributions)
    goal = SavingGoal(
        user_id=user.id, name=goal_name,
        description="Viaje de fin de año con la familia",
        target_amount=2_500_000, current_amount=total,
        deadline=date(today.year, 12, 20),
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    for amount, note, cdate in contributions:
        db.add(SavingContribution(goal_id=goal.id, amount=amount, note=note, date=cdate))
    db.commit()
    print(f"  [OK] Meta creada: {goal_name} — ${total:,.0f} de $2,500,000")

# ========================================================
# GRUPO COMPARTIDO
# ========================================================
print("\n-- Grupo compartido -------------------------------------")

group_name = "Apartamento compartido"
group = db.query(SharedGroup).filter(
    SharedGroup.creator_id == user.id, SharedGroup.name == group_name
).first()

if group:
    print(f"  * Ya existe grupo: {group_name}")
else:
    group = SharedGroup(name=group_name, description="Gastos del apartamento con roomie",
                         creator_id=user.id, group_type="gastos")
    db.add(group)
    db.flush()

    me = SharedGroupMember(group_id=group.id, name=user.full_name, email=user.email, user_id=user.id)
    roomie = SharedGroupMember(group_id=group.id, name="Andrés (roomie)", email=None, user_id=None)
    db.add_all([me, roomie])
    db.flush()

    expenses_data = [
        ("Mercado del mes", 180_000, "Mercado", ago(10), me.id),
        ("Internet hogar",   79_900, "Internet", ago(5), me.id),
        ("Gas compartido",   28_000, "Servicios públicos", ago(12), roomie.id),
    ]
    for desc, amount, cat, edate, payer_id in expenses_data:
        exp = SharedExpense(group_id=group.id, description=desc, amount=amount,
                             paid_by_id=payer_id, category=cat, date=edate)
        db.add(exp)
        db.flush()
        half = round(amount / 2, 2)
        for member_id in (me.id, roomie.id):
            is_payer = member_id == payer_id
            db.add(SharedExpenseSplit(expense_id=exp.id, member_id=member_id, amount=half,
                                       is_settled=is_payer))
    db.commit()
    print(f"  [OK] Grupo creado: {group_name} (2 miembros, {len(expenses_data)} gastos)")

# ========================================================
# ENTRENAR MODELOS ML
# ========================================================
print("\n-- Entrenando modelos ML ---------------------------------")
from services.ml_service import train_category_model, train_anomaly_model

all_txns = db.query(Transaction).filter(Transaction.user_id == user.id).all()
metrics = train_category_model(user.id, all_txns)
anom_ok = train_anomaly_model(user.id, all_txns)

if metrics:
    print(f"  [OK] Modelo de categorización entrenado")
    print(f"    Accuracy (CV-5) : {metrics['accuracy']:.1%}")
    print(f"    F1-weighted     : {metrics['f1_weighted']:.1%}")
    print(f"    Muestras        : {metrics['n_samples']}")
    print(f"    Categorías      : {metrics['n_categories']}")
else:
    print("  [!] Datos insuficientes para entrenar")

print(f"  {'[OK]' if anom_ok else '[!]'} Isolation Forest entrenado")

db.close()

print(f"""
==========================================================
  Seed de evaluación completado [OK]
==========================================================

  Credenciales:
    {EMAIL}  /  {PASSWORD}

  Incluye:
    * {len(gastos)} gastos + {len(ingresos)} ingresos (~5 meses de historia)
    * Transporte separado en "Transporte público" y
      "Transporte privado" con presupuestos independientes
    * {len(budgets_data)} presupuestos mensuales
    * 1 meta de ahorro con contribuciones
    * 1 grupo compartido con un miembro sin cuenta FinSmart
    * Modelos de IA entrenados (categorización + anomalías)
==========================================================
""")
