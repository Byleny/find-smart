"""
Datos para la sustentación — FinSmart

Crea (o actualiza) tres usuarios con ~7 meses de historia hasta hoy:

  · Isabel Realpe  (bylenosama@gmail.com): gastos e ingresos, presupuestos,
    metas de ahorro (impuesto vehicular, viaje de enero, SOAT, emergencias) y
    sus contratos de servicios (incluido el GDO 610257, que es real).
  · Elder Naspiran (elder.naspiran@finsmart.co): comparte con Isabel un grupo
    tipo *fondo* para los gastos del hogar — ambos aportan cada mes y los
    gastos se pagan del fondo.
  · Bylen Naspiran (bylen.naspiran@finsmart.co): comparte con Isabel un grupo
    tipo *gastos* — se turnan las suscripciones (Prime Video un mes uno, al
    otro mes el otro) y cuando Bylen paga algo Isabel le ayuda con una parte.

Todo lo generado lleva una marca invisible al final de la descripción (o va
en grupos/metas con nombre fijo), así que el script se puede correr varias
veces: borra lo que generó antes y lo vuelve a crear con fechas hasta hoy. No
toca transacciones, contratos ni grupos creados a mano.

Uso (en el contenedor del backend):
    SEED_CLAVE='<contraseña>' python seed_sustentacion.py
La contraseña de los tres usuarios se pasa por variable de entorno para no
dejarla escrita en el repositorio.
"""

import calendar
import os
import random
import sys
from datetime import date, datetime, timedelta

from database import Base, SessionLocal, engine
from models import (
    Budget, GroupFundContribution, Notification, RecurringService, SavingContribution,
    SavingGoal, SharedExpense, SharedExpenseSplit, SharedGroup, SharedGroupMember,
    Transaction, User,
)
from politica import POLITICA_VERSION
from security import get_password_hash

CLAVE = os.environ.get("SEED_CLAVE", "")
if len(CLAVE) < 6:
    sys.exit("Define SEED_CLAVE con la contraseña de los usuarios (mínimo 6 caracteres).")
MARCA = "​"  # sufijo invisible que identifica lo generado por este script

ISABEL = ("bylenosama@gmail.com", "Isabel Realpe")
ELDER = ("elder.naspiran@finsmart.co", "Elder Naspiran")
BYLEN = ("bylen.naspiran@finsmart.co", "Bylen Naspiran")

GRUPO_FONDO = "Hogar Isabel y Elder"
GRUPO_GASTOS = "Suscripciones y salidas"

METAS = [
    # (nombre, descripción, objetivo, fecha límite, aporte mensual base)
    ("Impuesto vehicular", "Impuesto del carro, vence en abril", 680_000, date(2027, 4, 30), 110_000),
    ("Viaje enero", "Viaje a Cartagena en enero", 3_500_000, date(2027, 1, 10), 450_000),
    ("SOAT", "Renovación del SOAT del carro", 520_000, date(2027, 2, 15), 70_000),
    ("Fondo de emergencia", "Tres meses de gastos básicos", 6_000_000, date(2027, 6, 30), 200_000),
]

# Progreso de Isabel con la app, del primer mes al último: el gasto variable
# baja a la mitad y los aportes a metas arrancan en el segundo mes y crecen.
GASTO_VARIABLE = (0.44, 0.38, 0.31, 0.26, 0.22, 0.19, 0.17)
RITMO_AHORRO = (0.0, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4)

# Categorías con presupuesto. El límite se calcula del gasto real de Isabel
# (ver presupuestos_isabel) para que en el mes actual esté dentro de todos.
PRESUPUESTOS = [
    "Alimentación", "Transporte", "Entretenimiento", "Salud", "Compras",
    "Servicios", "Gastos compartidos",
]
MARGEN_PRESUPUESTO = 1.2

hoy = date.today()
INICIO = date(hoy.year, hoy.month, 1)
for _ in range(6):  # seis meses completos antes del actual
    INICIO = (INICIO - timedelta(days=1)).replace(day=1)

rng = random.Random(20261030)
db = SessionLocal()


# ── Utilidades ────────────────────────────────────────────────────────────────

def meses():
    """(año, mes) desde INICIO hasta el mes actual."""
    y, m = INICIO.year, INICIO.month
    while (y, m) <= (hoy.year, hoy.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def dia(y, m, d):
    """Fecha del mes con el día ajustado al último del mes; None si es futura."""
    f = date(y, m, min(d, calendar.monthrange(y, m)[1]))
    return f if f <= hoy else None


def tx(user, desc, monto, cat, tipo, fecha):
    db.add(Transaction(user_id=user.id, description=desc + MARCA, amount=float(monto),
                       category=cat, type=tipo, date=fecha))


def usuario(email, nombre):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email, hashed_password="", full_name=nombre)
        db.add(u)
    u.full_name = nombre
    u.hashed_password = get_password_hash(CLAVE)
    u.politica_version = POLITICA_VERSION
    u.politica_aceptada_en = u.politica_aceptada_en or datetime.utcnow()
    db.flush()
    return u


def indice_mes(f):
    """Posición del mes de `f` dentro de la historia (0 = primer mes)."""
    return (f.year - INICIO.year) * 12 + f.month - INICIO.month


def gastos_variables(user, comercios, factor):
    """Gastos del día a día. `factor` es un número o una tupla por mes."""
    f = INICIO
    while f <= hoy:
        k = factor if isinstance(factor, float) else factor[min(indice_mes(f), len(factor) - 1)]
        for desc, (lo, hi), cat, prob in comercios:
            if rng.random() < prob * k:
                tx(user, desc, rng.randrange(lo // 100, hi // 100 + 1) * 100, cat, "gasto", f)
        f += timedelta(days=1)


# ── Limpieza de lo generado antes ─────────────────────────────────────────────

def limpiar(usuarios):
    ids = [u.id for u in usuarios]
    db.query(Transaction).filter(
        Transaction.user_id.in_(ids), Transaction.description.like(f"%{MARCA}%"),
    ).delete(synchronize_session=False)
    for g in db.query(SharedGroup).filter(
        SharedGroup.creator_id.in_(ids), SharedGroup.name.in_([GRUPO_FONDO, GRUPO_GASTOS]),
    ).all():
        db.query(Notification).filter(Notification.group_id == g.id).delete(synchronize_session=False)
        db.delete(g)  # cascada: miembros, gastos, divisiones y aportes
    for meta in db.query(SavingGoal).filter(
        SavingGoal.user_id.in_(ids), SavingGoal.name.in_([m[0] for m in METAS]),
    ).all():
        db.delete(meta)
    db.query(Budget).filter(
        Budget.user_id.in_(ids), Budget.category.in_(PRESUPUESTOS),
    ).delete(synchronize_session=False)
    db.flush()


# ── Isabel ────────────────────────────────────────────────────────────────────

def datos_isabel(isabel):
    for y, m in meses():
        for d in (14, 28):
            if (f := dia(y, m, d)):
                tx(isabel, "Pago nómina", 2_150_000, "Salario", "ingreso", f)
        for desc, monto, cat, d in [
            ("Cuota del carro", 780_000, "Transporte", 5),
            ("Plan celular Claro", 52_900, "Servicios", 8),
            ("Gimnasio Smart Fit", 75_000, "Salud", 3),
            ("Spotify", 16_900, "Entretenimiento", 12),
        ]:
            if (f := dia(y, m, d)):
                tx(isabel, desc, monto, cat, "gasto", f)

    gastos_variables(isabel, [
        ("Restaurante Platillos Voladores", (35_000, 70_000), "Alimentación", 0.35),
        ("Almuerzo corrientazo", (14_000, 19_000), "Alimentación", 1.0),
        ("Juan Valdez Café", (9_000, 18_000), "Alimentación", 0.6),
        ("Rappi", (25_000, 55_000), "Alimentación", 0.4),
        ("Estación Terpel", (60_000, 120_000), "Transporte", 0.45),
        ("Parqueadero Chipichape", (5_000, 12_000), "Transporte", 0.6),
        ("Uber", (9_000, 22_000), "Transporte", 0.4),
        ("Farmatodo", (18_000, 60_000), "Salud", 0.3),
        ("Cine Colombia", (20_000, 38_000), "Entretenimiento", 0.25),
        ("Falabella", (60_000, 220_000), "Compras", 0.2),
        ("Zara Unicentro", (90_000, 210_000), "Compras", 0.12),
    ], GASTO_VARIABLE)

    # Metas: aportes mensuales hasta hoy (cada aporte también es una transacción).
    for nombre, desc, objetivo, limite, mensual in METAS:
        meta = SavingGoal(user_id=isabel.id, name=nombre, description=desc,
                          target_amount=objetivo, current_amount=0, deadline=limite)
        db.add(meta)
        db.flush()
        for y, m in meses():
            if not (f := dia(y, m, 15)):
                continue
            ritmo = RITMO_AHORRO[min(indice_mes(f), len(RITMO_AHORRO) - 1)]
            monto = min(round(mensual * ritmo, -3), objetivo - meta.current_amount)
            if monto <= 0:
                continue
            db.add(SavingContribution(goal_id=meta.id, amount=monto, note="Aporte mensual", date=f))
            meta.current_amount += monto
            tx(isabel, f"Aporte meta: {nombre}", monto, "Ahorro", "gasto", f)

    # Contratos de servicios: el GDO 610257 es real (consulta de verdad al
    # portal). Solo se crean en la primera corrida: si el contrato ya existió
    # (aunque el usuario lo haya eliminado desde la app) no se vuelve a crear.
    contratos = [
        ("Gas casa", "gdo", "610257", "Servicios", 48_000, 10, "bylenosama@gmail.com"),
        ("Energía y agua EMCALI", "emcali", "562164", "Servicios", 185_000, 12, None),
        ("Plan celular", "claro", "3126266746", "Servicios", 52_900, 8, None),
    ]
    for nombre, prov, ref, cat, estimado, corte, correo in contratos:
        existe = db.query(RecurringService).filter(
            RecurringService.user_id == isabel.id, RecurringService.provider == prov,
            RecurringService.account_reference == ref,
        ).order_by(RecurringService.is_active.desc()).first()
        if not existe:
            db.add(RecurringService(
                user_id=isabel.id, name=nombre, provider=prov, account_reference=ref,
                category=cat, estimated_amount=estimado, billing_day=corte,
                payer_name=isabel.full_name, payer_email=correo,
            ))


# ── Elder ─────────────────────────────────────────────────────────────────────

def datos_elder(elder):
    for y, m in meses():
        if (f := dia(y, m, 1)):
            tx(elder, "Pensión", 2_400_000, "Salario", "ingreso", f)
        for desc, monto, cat, d in [
            ("Medicina prepagada", 310_000, "Salud", 6),
            ("Plan celular Movistar", 45_900, "Servicios", 9),
        ]:
            if (f := dia(y, m, d)):
                tx(elder, desc, monto, cat, "gasto", f)
    gastos_variables(elder, [
        ("Panadería La Espiga", (6_000, 15_000), "Alimentación", 1.0),
        ("Tienda de don Jairo", (5_000, 18_000), "Alimentación", 0.8),
        ("Droguería La Rebaja", (12_000, 45_000), "Salud", 0.35),
        ("Taxi", (9_000, 18_000), "Transporte", 0.5),
        ("Ferretería", (15_000, 80_000), "Compras", 0.15),
    ], 0.15)


# ── Bylen ─────────────────────────────────────────────────────────────────────

def datos_bylen(bylen):
    for y, m in meses():
        for d in (15, 31):
            if (f := dia(y, m, d)):
                tx(bylen, "Pago nómina", 1_650_000, "Salario", "ingreso", f)
        if (f := dia(y, m, 2)):
            tx(bylen, "Arriendo habitación", 650_000, "Vivienda", "gasto", f)
    gastos_variables(bylen, [
        ("Almuerzo universidad", (12_000, 18_000), "Alimentación", 1.0),
        ("D1", (15_000, 40_000), "Alimentación", 0.5),
        ("MIO recarga", (10_000, 20_000), "Transporte", 0.6),
        ("Steam", (20_000, 90_000), "Entretenimiento", 0.12),
    ], 0.17)


# ── Grupo tipo fondo: Isabel y Elder ─────────────────────────────────────────

def grupo_fondo(isabel, elder):
    g = SharedGroup(name=GRUPO_FONDO, description="Fondo común para los gastos de la casa",
                    creator_id=isabel.id, group_type="fondo")
    db.add(g)
    db.flush()
    mi = SharedGroupMember(group_id=g.id, user_id=isabel.id, name=isabel.full_name, email=isabel.email)
    me = SharedGroupMember(group_id=g.id, user_id=elder.id, name=elder.full_name, email=elder.email)
    db.add_all([mi, me])
    db.flush()

    for y, m in meses():
        # Aportes al fondo a inicio de mes (cada uno es un gasto del que aporta).
        for miembro, user, monto in ((mi, isabel, 700_000), (me, elder, 700_000)):
            if (f := dia(y, m, 2)):
                db.add(GroupFundContribution(group_id=g.id, member_id=miembro.id, amount=monto,
                                             note="Aporte mensual", date=f))
                tx(user, f"Aporte al fondo {GRUPO_FONDO}: Aporte mensual", monto, "Gastos compartidos", "gasto", f)
        # Gastos pagados con el dinero del fondo (no generan transacción personal).
        gastos = [
            ("Mercado del mes Éxito", rng.randrange(3_200, 4_100) * 100, "Alimentación", 4, mi),
            ("Factura EMCALI", rng.randrange(1_650, 2_050) * 100, "Servicios", 13, me),
            ("Factura gas GDO", rng.randrange(420, 560) * 100, "Servicios", 11, mi),
            ("Internet hogar", 95_000, "Servicios", 7, me),
            ("Mercado de la quincena La 14", rng.randrange(1_500, 2_100) * 100, "Alimentación", 18, mi),
            ("Aseo y droguería", rng.randrange(600, 1_100) * 100, "Compras", 22, me),
        ]
        for desc, monto, cat, d, pagador in gastos:
            if (f := dia(y, m, d)):
                db.add(SharedExpense(group_id=g.id, description=desc, amount=monto,
                                     paid_by_id=pagador.id, category=cat, date=f))


# ── Grupo tipo gastos: Isabel y Bylen ────────────────────────────────────────

def grupo_gastos(isabel, bylen):
    g = SharedGroup(name=GRUPO_GASTOS, description="Suscripciones y salidas entre Isabel y Bylen",
                    creator_id=isabel.id, group_type="gastos")
    db.add(g)
    db.flush()
    mi = SharedGroupMember(group_id=g.id, user_id=isabel.id, name=isabel.full_name, email=isabel.email)
    mb = SharedGroupMember(group_id=g.id, user_id=bylen.id, name=bylen.full_name, email=bylen.email)
    db.add_all([mi, mb])
    db.flush()
    socios = {mi.id: (mi, isabel), mb.id: (mb, bylen)}
    mes_actual = (hoy.year, hoy.month)

    def gasto(desc, monto, cat, fecha, pagador, parte_otro):
        """El pagador cubre todo; el otro le debe `parte_otro`. Saldado salvo el mes actual."""
        otro = mb if pagador is mi else mi
        e = SharedExpense(group_id=g.id, description=desc, amount=monto,
                          paid_by_id=pagador.id, category=cat, date=fecha)
        db.add(e)
        db.flush()
        ahora = datetime.combine(fecha, datetime.min.time())
        db.add(SharedExpenseSplit(expense_id=e.id, member_id=pagador.id, amount=monto - parte_otro,
                                  is_settled=True, settled_at=ahora))
        saldado = (fecha.year, fecha.month) != mes_actual
        db.add(SharedExpenseSplit(
            expense_id=e.id, member_id=otro.id, amount=parte_otro, is_settled=saldado,
            settled_at=ahora + timedelta(days=5) if saldado else None,
            settled_by_user_id=socios[pagador.id][1].id if saldado else None,
        ))
        tx(socios[pagador.id][1], f"{desc} · {GRUPO_GASTOS}", monto, "Gastos compartidos", "gasto", fecha)

    for i, (y, m) in enumerate(meses()):
        # Prime Video: un mes paga Bylen, al siguiente Isabel; mitad y mitad.
        if (f := dia(y, m, 6)):
            pagador = mb if i % 2 == 0 else mi
            gasto("Prime Video", 14_900, "Entretenimiento", f, pagador, 7_450)
        # Netflix lo paga Bylen e Isabel le ayuda con una parte.
        if (f := dia(y, m, 14)):
            gasto("Netflix", 26_900, "Entretenimiento", f, mb, 13_450)
        # Salidas: Bylen paga y Isabel pone una parte (40 %).
        if (f := dia(y, m, rng.randint(17, 26))):
            monto = rng.randrange(700, 1_400) * 100
            gasto(rng.choice(["Cena Crepes & Waffles", "Pizza Tiramisú", "Cine y crispetas"]),
                  monto, "Entretenimiento", f, mb, round(monto * 0.4))
        # Mercado pequeño que paga Isabel; Bylen pone la mitad.
        if (f := dia(y, m, 24)):
            monto = rng.randrange(450, 900) * 100
            gasto("Mercado D1 para la casa", monto, "Alimentación", f, mi, monto // 2)


# ── Presupuestos de Isabel ───────────────────────────────────────────────────

def presupuestos_isabel(isabel):
    """
    Límite = el mayor entre el gasto del mes actual y el promedio de los tres
    meses anteriores, más un 20 % de margen, redondeado a 50.000. Así el mes
    actual queda dentro de todos sus presupuestos, como alguien que ya los
    ajustó a su realidad. Va después de los grupos porque los pagos
    compartidos también cuentan en "Gastos compartidos".
    """
    db.flush()
    actual = date(hoy.year, hoy.month, 1)
    anteriores = (actual - timedelta(days=1)).replace(day=1)
    for _ in range(2):
        anteriores = (anteriores - timedelta(days=1)).replace(day=1)
    for cat in PRESUPUESTOS:
        gastos = db.query(Transaction).filter(
            Transaction.user_id == isabel.id, Transaction.type == "gasto",
            Transaction.category == cat, Transaction.date >= anteriores,
        ).all()
        mes_actual = sum(t.amount for t in gastos if t.date >= actual)
        promedio = sum(t.amount for t in gastos if t.date < actual) / 3
        base = max(mes_actual, promedio)
        if base <= 0:
            continue
        limite = -(-base * MARGEN_PRESUPUESTO // 50_000) * 50_000
        db.add(Budget(user_id=isabel.id, category=cat, limit_amount=limite, period="monthly"))


# ── Ejecución ─────────────────────────────────────────────────────────────────

def main():
    Base.metadata.create_all(bind=engine)
    isabel, elder, bylen = usuario(*ISABEL), usuario(*ELDER), usuario(*BYLEN)
    limpiar([isabel, elder, bylen])
    datos_isabel(isabel)
    datos_elder(elder)
    datos_bylen(bylen)
    grupo_fondo(isabel, elder)
    grupo_gastos(isabel, bylen)
    presupuestos_isabel(isabel)
    db.commit()

    print(f"Historia desde {INICIO} hasta {hoy}.")
    for u in (isabel, elder, bylen):
        n = db.query(Transaction).filter(Transaction.user_id == u.id).count()
        print(f"  {u.full_name:16s} {u.email:30s} id={u.id:<4d} transacciones={n}")
    for meta in db.query(SavingGoal).filter(SavingGoal.user_id == isabel.id).all():
        print(f"  Meta {meta.name}: {meta.current_amount:,.0f} / {meta.target_amount:,.0f}")


if __name__ == "__main__":
    main()
