"""
Seed completo – FinSmart
========================
Crea un escenario realista con:
  * 3 usuarios enlazados + 1 miembro sin cuenta
  * 6 meses de transacciones para el usuario principal (Ana)
  * Grupo familiar con gastos compartidos y splits (algunos saldados)
  * Presupuestos mensuales por categoría
  * Metas de ahorro con contribuciones
  * Modelos ML entrenados al final

Credenciales:
  demo@finsmart.co  /  demo1234   <- usuario principal (Ana García)
  carlos@finsmart.co / demo1234   <- Carlos García (pareja)
  lucia@finsmart.co  / demo1234   <- Lucía García (hermana)
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

from datetime import date, datetime, timedelta
from sqlalchemy import text as _sql_text
from database import SessionLocal, engine, Base
from models import (
    User, Transaction,
    Budget, SavingGoal, SavingContribution,
    SharedGroup, SharedGroupMember, SharedExpense, SharedExpenseSplit,
    GroupFundContribution,
)
from security import get_password_hash

Base.metadata.create_all(bind=engine)
with engine.connect() as _c:
    for _s in [
        "ALTER TABLE shared_group_members ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE shared_group_members ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE users ADD COLUMN phone TEXT",
        "ALTER TABLE users ADD COLUMN identification_type TEXT DEFAULT 'CC'",
        "ALTER TABLE users ADD COLUMN identification_number TEXT",
        "ALTER TABLE recurring_services ADD COLUMN payer_name TEXT",
        "ALTER TABLE recurring_services ADD COLUMN payer_id_type TEXT",
        "ALTER TABLE recurring_services ADD COLUMN payer_id_number TEXT",
        "ALTER TABLE recurring_services ADD COLUMN payer_phone TEXT",
        "ALTER TABLE recurring_services ADD COLUMN payer_email TEXT",
        "ALTER TABLE saving_contributions ADD COLUMN date TEXT DEFAULT (date('now'))",
        "ALTER TABLE saving_goals ADD COLUMN current_amount REAL DEFAULT 0.0",
        "ALTER TABLE shared_groups ADD COLUMN group_type TEXT NOT NULL DEFAULT 'gastos'",
    ]:
        try:
            _c.execute(_sql_text(_s)); _c.commit()
        except Exception:
            pass

db = SessionLocal()
today = date.today()

def ago(days: int) -> date:
    return today - timedelta(days=days)

# ========================================================
# 1. USUARIOS
# ========================================================

def upsert_user(email, name, pwd="demo1234"):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        u = User(email=email, hashed_password=get_password_hash(pwd), full_name=name)
        db.add(u); db.commit(); db.refresh(u)
        print(f"  [OK] Usuario creado: {email}")
    else:
        print(f"  * Ya existe: {email}")
    return u

print("\n-- Usuarios ------------------------------------------")
ana    = upsert_user("demo@finsmart.co",   "Ana García")
carlos = upsert_user("carlos@finsmart.co", "Carlos García")
lucia  = upsert_user("lucia@finsmart.co",  "Lucía García")

# ========================================================
# 2. TRANSACCIONES DE ANA (usuario principal)
# ========================================================
print("\n-- Transacciones de Ana ------------------------------")

gastos_ana = [
    # ---- ALIMENTACIÓN ----
    # Meses 1-4 (últimos ~120 días)
    ("Supermercado Éxito",        38_000, "Alimentación", ago(2)),
    ("Supermercado Éxito",        41_000, "Alimentación", ago(32)),
    ("Supermercado Éxito",        39_500, "Alimentación", ago(62)),
    ("Supermercado Éxito",        37_000, "Alimentación", ago(92)),
    ("Mercado La 14",             27_000, "Alimentación", ago(10)),
    ("Mercado La 14",             25_500, "Alimentación", ago(40)),
    ("Mercado La 14",             28_000, "Alimentación", ago(70)),
    ("Mercado La 14",             26_500, "Alimentación", ago(100)),
    ("Restaurante El Patio",      22_000, "Alimentación", ago(5)),
    ("Restaurante El Patio",      19_500, "Alimentación", ago(35)),
    ("Restaurante El Bonito",     24_000, "Alimentación", ago(18)),
    ("Pizza Hut",                 32_000, "Alimentación", ago(48)),
    ("Pizza domicilio",           28_000, "Alimentación", ago(20)),
    ("Domicilio comida",          18_500, "Alimentación", ago(8)),
    ("Domicilio comida",          21_000, "Alimentación", ago(55)),
    ("Frutas y verduras",          8_500, "Alimentación", ago(7)),
    ("Frutas y verduras",          9_000, "Alimentación", ago(37)),
    ("Tienda del barrio",          6_200, "Alimentación", ago(3)),
    ("Tienda del barrio",          5_800, "Alimentación", ago(33)),
    ("Tienda del barrio",          7_100, "Alimentación", ago(63)),
    ("Pan y café",                 5_500, "Alimentación", ago(14)),
    ("Cafetería oficina",          4_800, "Alimentación", ago(4)),
    ("Cafetería oficina",          5_200, "Alimentación", ago(24)),
    ("Rappi mercado",             45_000, "Alimentación", ago(11)),
    ("Rappi mercado",             38_000, "Alimentación", ago(41)),
    # Mes 5 (Mar 2026)
    ("Supermercado Éxito",        36_500, "Alimentación", ago(122)),
    ("Mercado La 14",             24_500, "Alimentación", ago(130)),
    ("Restaurante El Patio",      20_500, "Alimentación", ago(125)),
    ("Domicilio comida",          17_000, "Alimentación", ago(133)),
    ("Frutas y verduras",          8_200, "Alimentación", ago(137)),
    ("Tienda del barrio",          6_500, "Alimentación", ago(143)),
    ("Rappi mercado",             37_000, "Alimentación", ago(141)),
    ("Pan y café",                 5_300, "Alimentación", ago(144)),
    ("Cafetería oficina",          4_600, "Alimentación", ago(134)),
    # Mes 6 (Feb 2026)
    ("Supermercado Éxito",        35_000, "Alimentación", ago(152)),
    ("Mercado La 14",             23_500, "Alimentación", ago(160)),
    ("Restaurante El Patio",      21_000, "Alimentación", ago(155)),
    ("Domicilio comida",          16_000, "Alimentación", ago(163)),
    ("Frutas y verduras",          7_800, "Alimentación", ago(167)),
    ("Tienda del barrio",          6_200, "Alimentación", ago(173)),
    ("Rappi mercado",             36_000, "Alimentación", ago(171)),
    ("Cafetería oficina",          4_400, "Alimentación", ago(164)),

    # ---- TRANSPORTE ----
    # Meses 1-4
    ("Uber",                      12_000, "Transporte", ago(1)),
    ("Uber",                      15_000, "Transporte", ago(8)),
    ("Uber",                      11_500, "Transporte", ago(15)),
    ("Uber",                      13_000, "Transporte", ago(22)),
    ("Uber",                      14_000, "Transporte", ago(29)),
    ("Uber",                      16_000, "Transporte", ago(75)),
    ("InDriver",                  10_500, "Transporte", ago(9)),
    ("InDriver",                  12_000, "Transporte", ago(39)),
    ("MIO tarjeta recarga",        5_000, "Transporte", ago(30)),
    ("MIO tarjeta recarga",        5_000, "Transporte", ago(60)),
    ("MIO tarjeta recarga",        5_000, "Transporte", ago(90)),
    ("MIO tarjeta recarga",        5_000, "Transporte", ago(120)),
    ("Taxi",                       9_000, "Transporte", ago(12)),
    ("Taxi",                       8_500, "Transporte", ago(42)),
    ("Parqueadero centro",         4_000, "Transporte", ago(6)),
    ("Parqueadero centro",         4_000, "Transporte", ago(26)),
    ("Gasolina vehículo",         80_000, "Transporte", ago(15)),
    ("Gasolina vehículo",         75_000, "Transporte", ago(45)),
    # Mes 5
    ("Uber",                      13_500, "Transporte", ago(128)),
    ("Uber",                      12_000, "Transporte", ago(135)),
    ("Uber",                      15_000, "Transporte", ago(143)),
    ("MIO tarjeta recarga",        5_000, "Transporte", ago(150)),
    ("Taxi",                       9_000, "Transporte", ago(132)),
    ("InDriver",                  11_000, "Transporte", ago(139)),
    ("Gasolina vehículo",         77_000, "Transporte", ago(135)),
    # Mes 6
    ("Uber",                      12_500, "Transporte", ago(158)),
    ("Uber",                      14_000, "Transporte", ago(165)),
    ("MIO tarjeta recarga",        5_000, "Transporte", ago(180)),
    ("Taxi",                       8_500, "Transporte", ago(162)),
    ("InDriver",                  10_500, "Transporte", ago(169)),
    ("Gasolina vehículo",         74_000, "Transporte", ago(165)),

    # ---- SERVICIOS ----
    # Meses 1-4
    ("Claro internet hogar",      79_900, "Servicios", ago(5)),
    ("Claro internet hogar",      79_900, "Servicios", ago(35)),
    ("Claro internet hogar",      79_900, "Servicios", ago(65)),
    ("Claro internet hogar",      79_900, "Servicios", ago(95)),
    ("Acueducto EMCALI",          45_000, "Servicios", ago(10)),
    ("Acueducto EMCALI",          47_200, "Servicios", ago(40)),
    ("Acueducto EMCALI",          44_800, "Servicios", ago(70)),
    ("Acueducto EMCALI",          46_000, "Servicios", ago(100)),
    ("Gas GDO",                   28_000, "Servicios", ago(12)),
    ("Gas GDO",                   31_000, "Servicios", ago(42)),
    ("Gas GDO",                   29_500, "Servicios", ago(72)),
    ("Gas GDO",                   30_000, "Servicios", ago(102)),
    ("Energía Enel",              55_000, "Servicios", ago(8)),
    ("Energía Enel",              58_000, "Servicios", ago(38)),
    ("Energía Enel",              57_000, "Servicios", ago(68)),
    ("Energía Enel",              54_000, "Servicios", ago(98)),
    ("Plan celular Claro",        39_900, "Servicios", ago(3)),
    ("Plan celular Claro",        39_900, "Servicios", ago(33)),
    ("Plan celular Claro",        39_900, "Servicios", ago(63)),
    ("Plan celular Claro",        39_900, "Servicios", ago(93)),
    # Mes 5
    ("Claro internet hogar",      79_900, "Servicios", ago(125)),
    ("Acueducto EMCALI",          43_000, "Servicios", ago(130)),
    ("Gas GDO",                   27_000, "Servicios", ago(132)),
    ("Energía Enel",              53_000, "Servicios", ago(128)),
    ("Plan celular Claro",        39_900, "Servicios", ago(123)),
    # Mes 6
    ("Claro internet hogar",      79_900, "Servicios", ago(155)),
    ("Acueducto EMCALI",          44_000, "Servicios", ago(160)),
    ("Gas GDO",                   30_000, "Servicios", ago(162)),
    ("Energía Enel",              56_000, "Servicios", ago(158)),
    ("Plan celular Claro",        39_900, "Servicios", ago(153)),

    # ---- ENTRETENIMIENTO ----
    # Meses 1-4
    ("Netflix",                   22_900, "Entretenimiento", ago(3)),
    ("Netflix",                   22_900, "Entretenimiento", ago(33)),
    ("Netflix",                   22_900, "Entretenimiento", ago(63)),
    ("Netflix",                   22_900, "Entretenimiento", ago(93)),
    ("Spotify",                   10_900, "Entretenimiento", ago(6)),
    ("Spotify",                   10_900, "Entretenimiento", ago(36)),
    ("Spotify",                   10_900, "Entretenimiento", ago(66)),
    ("Spotify",                   10_900, "Entretenimiento", ago(96)),
    ("Cine Colombia",             19_000, "Entretenimiento", ago(14)),
    ("Cine Colombia",             21_000, "Entretenimiento", ago(44)),
    ("Cinemark",                  18_500, "Entretenimiento", ago(28)),
    ("Juego en línea",            15_000, "Entretenimiento", ago(20)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(7)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(37)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(67)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(97)),
    ("Concierto",                 85_000, "Entretenimiento", ago(50)),
    # Mes 5
    ("Netflix",                   22_900, "Entretenimiento", ago(123)),
    ("Spotify",                   10_900, "Entretenimiento", ago(126)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(127)),
    ("Cine Colombia",             20_000, "Entretenimiento", ago(134)),
    # Mes 6
    ("Netflix",                   22_900, "Entretenimiento", ago(153)),
    ("Spotify",                   10_900, "Entretenimiento", ago(156)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(157)),

    # ---- SALUD ----
    # Meses 1-4
    ("Droguería Cruz Verde",      15_000, "Salud", ago(20)),
    ("Droguería Cruz Verde",      22_000, "Salud", ago(50)),
    ("Droguería Cruz Verde",      18_000, "Salud", ago(80)),
    ("Droguería La Rebaja",       12_000, "Salud", ago(15)),
    ("Médico particular",         60_000, "Salud", ago(25)),
    ("Médico particular",         65_000, "Salud", ago(85)),
    ("Gimnasio Smart Fit",        65_000, "Salud", ago(1)),
    ("Gimnasio Smart Fit",        65_000, "Salud", ago(31)),
    ("Gimnasio Smart Fit",        65_000, "Salud", ago(61)),
    ("Gimnasio Smart Fit",        65_000, "Salud", ago(91)),
    ("Farmacia Pasteur",          25_000, "Salud", ago(10)),
    ("Odontólogo",                80_000, "Salud", ago(45)),
    ("Laboratorio clínico",       45_000, "Salud", ago(30)),
    # Mes 5
    ("Droguería Cruz Verde",      14_000, "Salud", ago(130)),
    ("Gimnasio Smart Fit",        65_000, "Salud", ago(121)),
    ("Farmacia Pasteur",          22_000, "Salud", ago(140)),
    # Mes 6
    ("Droguería Cruz Verde",      16_000, "Salud", ago(160)),
    ("Gimnasio Smart Fit",        65_000, "Salud", ago(151)),
    ("Farmacia Pasteur",          20_000, "Salud", ago(170)),

    # ---- VIVIENDA ----
    # Meses 1-4
    ("Arriendo apartamento",     900_000, "Vivienda", ago(5)),
    ("Arriendo apartamento",     900_000, "Vivienda", ago(35)),
    ("Arriendo apartamento",     900_000, "Vivienda", ago(65)),
    ("Arriendo apartamento",     900_000, "Vivienda", ago(95)),
    ("Administración",            95_000, "Vivienda", ago(8)),
    ("Administración",            95_000, "Vivienda", ago(38)),
    ("Administración",            95_000, "Vivienda", ago(68)),
    ("Administración",            95_000, "Vivienda", ago(98)),
    ("Reparación plomería",       80_000, "Vivienda", ago(22)),
    ("Pintura habitación",       150_000, "Vivienda", ago(60)),
    ("Artículos hogar",           45_000, "Vivienda", ago(17)),
    # Mes 5
    ("Arriendo apartamento",     900_000, "Vivienda", ago(125)),
    ("Administración",            95_000, "Vivienda", ago(128)),
    ("Artículos hogar",           38_000, "Vivienda", ago(137)),
    # Mes 6
    ("Arriendo apartamento",     900_000, "Vivienda", ago(155)),
    ("Administración",            95_000, "Vivienda", ago(158)),

    # ---- ANOMALÍAS plantadas para Isolation Forest ----
    ("Supermercado Éxito",       520_000, "Alimentación",    ago(16)),
    ("Uber",                     180_000, "Transporte",      ago(9)),
    ("Cine Colombia",            350_000, "Entretenimiento", ago(21)),
    ("Droguería Cruz Verde",     280_000, "Salud",           ago(55)),
]

ingresos_ana = [
    ("Salario octubre",    3_200_000, "Salario",   ago(115)),
    ("Salario noviembre",  3_200_000, "Salario",   ago(85)),
    ("Salario diciembre",  3_200_000, "Salario",   ago(55)),
    ("Salario enero",      3_350_000, "Salario",   ago(25)),
    ("Salario marzo",      3_200_000, "Salario",   ago(145)),
    ("Salario febrero",    3_200_000, "Salario",   ago(175)),
    ("Freelance diseño",     450_000, "Freelance", ago(45)),
    ("Freelance video",      320_000, "Freelance", ago(70)),
    ("Freelance diseño",     300_000, "Freelance", ago(140)),
    ("Venta celular usado",  380_000, "Ventas",    ago(30)),
    ("Bonificación",         500_000, "Salario",   ago(20)),
]

existing_keys = {
    (t.description, str(t.date))
    for t in db.query(Transaction).filter(Transaction.user_id == ana.id).all()
}

added = 0
for desc, amount, cat, tdate in gastos_ana:
    if (desc, str(tdate)) not in existing_keys:
        db.add(Transaction(user_id=ana.id, description=desc, amount=amount,
                           category=cat, type="gasto", date=tdate))
        added += 1
for desc, amount, cat, tdate in ingresos_ana:
    if (desc, str(tdate)) not in existing_keys:
        db.add(Transaction(user_id=ana.id, description=desc, amount=amount,
                           category=cat, type="ingreso", date=tdate))
        added += 1

db.commit()
print(f"  [OK] {added} transacciones agregadas a Ana")

# ========================================================
# 3. PRESUPUESTOS DE ANA
# ========================================================
print("\n-- Presupuestos de Ana -------------------------------")

budgets_data = [
    ("Alimentación",    400_000),
    ("Transporte",      200_000),
    ("Servicios",       320_000),
    ("Entretenimiento", 130_000),
    ("Salud",           150_000),
    ("Vivienda",      1_050_000),
]

for cat, limit in budgets_data:
    exists = db.query(Budget).filter(
        Budget.user_id == ana.id, Budget.category == cat
    ).first()
    if not exists:
        db.add(Budget(user_id=ana.id, category=cat, limit_amount=limit, period="monthly"))
        print(f"  [OK] Presupuesto {cat}: ${limit:,.0f}")
    else:
        print(f"  * Ya existe presupuesto: {cat}")

db.commit()

# ========================================================
# 4. METAS DE AHORRO + CONTRIBUCIONES
# ========================================================
print("\n-- Metas de ahorro de Ana ----------------------------")

goals_data = [
    {
        "name": "Vacaciones Cartagena",
        "description": "Viaje familiar a Cartagena en diciembre",
        "target": 2_000_000,
        "deadline": date(2026, 12, 15),
        "contributions": [
            (200_000, "Ahorro mes octubre",  ago(110)),
            (200_000, "Ahorro mes noviembre",ago(80)),
            (150_000, "Ahorro mes diciembre",ago(50)),
            (150_000, "Ahorro mes enero",    ago(20)),
            (150_000, "Extra freelance",     ago(44)),
        ],
    },
    {
        "name": "Fondo de emergencia",
        "description": "3 meses de gastos como colchón financiero",
        "target": 5_000_000,
        "deadline": date(2026, 12, 31),
        "contributions": [
            (300_000, "Ahorro octubre",  ago(112)),
            (300_000, "Ahorro noviembre",ago(82)),
            (250_000, "Ahorro diciembre",ago(52)),
            (350_000, "Ahorro enero",    ago(22)),
        ],
    },
    {
        "name": "Computador nuevo",
        "description": "MacBook para trabajo remoto",
        "target": 3_500_000,
        "deadline": date(2026, 6, 30),
        "contributions": [
            (500_000, "Ingreso venta celular", ago(30)),
            (700_000, "Ahorro noviembre",      ago(82)),
            (600_000, "Ahorro diciembre",      ago(52)),
            (500_000, "Freelance diseño",      ago(45)),
            (500_000, "Ahorro enero",          ago(22)),
        ],
    },
]

for g in goals_data:
    existing_goal = db.query(SavingGoal).filter(
        SavingGoal.user_id == ana.id, SavingGoal.name == g["name"]
    ).first()

    if existing_goal:
        print(f"  * Ya existe meta: {g['name']}")
        goal = existing_goal
    else:
        total = sum(c[0] for c in g["contributions"])
        goal = SavingGoal(
            user_id=ana.id,
            name=g["name"],
            description=g["description"],
            target_amount=g["target"],
            current_amount=total,
            deadline=g["deadline"],
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        print(f"  [OK] Meta creada: {g['name']} → ${total:,.0f} / ${g['target']:,.0f}")

        for amount, note, cdate in g["contributions"]:
            db.add(SavingContribution(
                goal_id=goal.id, amount=amount, note=note, date=cdate,
            ))
        db.commit()

# ========================================================
# 5. GRUPO FAMILIAR + GASTOS COMPARTIDOS
# ========================================================
print("\n-- Grupo familiar ------------------------------------")

group = db.query(SharedGroup).filter(SharedGroup.name == "Familia García").first()
if not group:
    group = SharedGroup(name="Familia García",
                        description="Gastos compartidos del hogar y actividades en familia",
                        creator_id=ana.id)
    db.add(group)
    db.commit()
    db.refresh(group)
    print(f"  [OK] Grupo creado: Familia García (id={group.id})")
else:
    print(f"  * Grupo ya existe (id={group.id})")

gid = group.id

def get_or_create_member(user_obj, display_name):
    m = db.query(SharedGroupMember).filter(
        SharedGroupMember.group_id == gid,
        SharedGroupMember.user_id == user_obj.id,
    ).first()
    if not m:
        m = SharedGroupMember(
            group_id=gid, user_id=user_obj.id,
            name=display_name, email=user_obj.email,
        )
        db.add(m); db.commit(); db.refresh(m)
        print(f"  [OK] Miembro agregado: {display_name}")
    return m

def get_or_create_external_member(name):
    m = db.query(SharedGroupMember).filter(
        SharedGroupMember.group_id == gid,
        SharedGroupMember.name == name,
        SharedGroupMember.user_id == None,
    ).first()
    if not m:
        m = SharedGroupMember(group_id=gid, name=name, user_id=None)
        db.add(m); db.commit(); db.refresh(m)
        print(f"  [OK] Miembro externo agregado: {name}")
    return m

m_ana    = get_or_create_member(ana,    "Ana García")
m_carlos = get_or_create_member(carlos, "Carlos García")
m_lucia  = get_or_create_member(lucia,  "Lucía García")
m_papa   = get_or_create_external_member("Papá")

all_members = [m_ana, m_carlos, m_lucia, m_papa]

def add_shared_expense(description, total, category, expense_date,
                        paid_by, splits, settled_members=None):
    """
    splits: lista de (member, amount)
    settled_members: lista de members cuyo split ya fue saldado
    """
    settled_members = settled_members or []

    existing = db.query(SharedExpense).filter(
        SharedExpense.group_id == gid,
        SharedExpense.description == description,
        SharedExpense.date == expense_date,
    ).first()
    if existing:
        return

    exp = SharedExpense(
        group_id=gid,
        description=description,
        amount=total,
        paid_by_id=paid_by.id,
        category=category,
        date=expense_date,
    )
    db.add(exp); db.commit(); db.refresh(exp)

    for member, split_amount in splits:
        is_payer = (member.id == paid_by.id)
        is_settled = is_payer or (member in settled_members)
        db.add(SharedExpenseSplit(
            expense_id=exp.id,
            member_id=member.id,
            amount=round(split_amount, 2),
            is_settled=is_settled,
            settled_at=datetime.utcnow() if is_settled and not is_payer else None,
        ))

    db.commit()

print("\n-- Gastos compartidos --------------------------------")

# -- Mercado mensual (Ana paga, divide entre los 4) ------
for d, note in [(ago(5), "Mercado enero"), (ago(35), "Mercado diciembre"),
                (ago(65), "Mercado noviembre"), (ago(95), "Mercado octubre")]:
    settled = [m_carlos] if d <= ago(65) else []
    add_shared_expense(
        f"Mercado familiar · {note}", 240_000, "Alimentación", d,
        paid_by=m_ana,
        splits=[(m, 60_000) for m in all_members],
        settled_members=settled,
    )

# -- Arriendo cuarto extra (Carlos paga, divide Ana+Carlos) --
for d in [ago(5), ago(35), ago(65), ago(95)]:
    settled = [m_ana] if d <= ago(35) else []
    add_shared_expense(
        "Arriendo cuarto estudio", 600_000, "Vivienda", d,
        paid_by=m_carlos,
        splits=[(m_ana, 300_000), (m_carlos, 300_000)],
        settled_members=settled,
    )

# -- Internet compartido (Carlos paga, Ana+Carlos) --
for d in [ago(4), ago(34), ago(64), ago(94)]:
    add_shared_expense(
        "Claro internet compartido", 79_900, "Servicios", d,
        paid_by=m_carlos,
        splits=[(m_ana, 39_950), (m_carlos, 39_950)],
        settled_members=[m_ana] if d <= ago(34) else [],
    )

# -- Cena cumpleaños papá (Lucía paga, divide los 4) --
add_shared_expense(
    "Cena cumpleaños papá", 280_000, "Alimentación", ago(48),
    paid_by=m_lucia,
    splits=[(m, 70_000) for m in all_members],
    settled_members=[m_ana, m_carlos],
)

# -- Paseo a Buga (Ana paga, los 4) --
add_shared_expense(
    "Paseo familiar a Buga", 520_000, "Entretenimiento", ago(72),
    paid_by=m_ana,
    splits=[(m, 130_000) for m in all_members],
    settled_members=[m_carlos, m_lucia, m_papa],
)

# -- Cine familiar (Lucía paga, Ana+Carlos+Lucía) --
add_shared_expense(
    "Cine Colombia · función familiar", 84_000, "Entretenimiento", ago(14),
    paid_by=m_lucia,
    splits=[(m_ana, 28_000), (m_carlos, 28_000), (m_lucia, 28_000)],
    settled_members=[],
)

# -- Regalos navidad (Ana paga, los 4) --
add_shared_expense(
    "Regalos navidad en familia", 480_000, "Entretenimiento", ago(55),
    paid_by=m_ana,
    splits=[(m, 120_000) for m in all_members],
    settled_members=[m_carlos],
)

# -- Mercado especial semana santa (Carlos paga, los 4) --
add_shared_expense(
    "Mercado semana santa", 180_000, "Alimentación", ago(40),
    paid_by=m_carlos,
    splits=[(m, 45_000) for m in all_members],
    settled_members=[m_ana, m_lucia, m_papa],
)

# -- Tinto y desayuno oficina (Ana paga, Ana+Carlos) --
for d in [ago(3), ago(17), ago(31)]:
    add_shared_expense(
        "Desayuno oficina", 28_000, "Alimentación", d,
        paid_by=m_ana,
        splits=[(m_ana, 14_000), (m_carlos, 14_000)],
        settled_members=[m_carlos] if d <= ago(17) else [],
    )

# -- Mantenimiento carro (papá paga, Ana+Carlos+Papá) --
add_shared_expense(
    "Mantenimiento carro familiar", 350_000, "Transporte", ago(30),
    paid_by=m_papa,
    splits=[(m_ana, 116_667), (m_carlos, 116_667), (m_papa, 116_666)],
    settled_members=[m_ana],
)

print(f"  [OK] Gastos compartidos creados")

# ========================================================
# 6. FONDO COMÚN FAMILIA GARCÍA
# ========================================================
print("\n-- Fondo Familiar García -----------------------------")

fondo = db.query(SharedGroup).filter(SharedGroup.name == "Fondo Familiar García").first()
if not fondo:
    fondo = SharedGroup(
        name="Fondo Familiar García",
        description="Fondo común para gastos del hogar",
        creator_id=ana.id,
        group_type="fondo",
    )
    db.add(fondo); db.commit(); db.refresh(fondo)
    print(f"  [OK] Grupo fondo creado (id={fondo.id})")
else:
    print(f"  * Fondo ya existe (id={fondo.id})")

fid = fondo.id

def get_or_create_fund_member(user_obj, display_name):
    m = db.query(SharedGroupMember).filter(
        SharedGroupMember.group_id == fid,
        SharedGroupMember.user_id == user_obj.id,
    ).first()
    if not m:
        m = SharedGroupMember(group_id=fid, user_id=user_obj.id, name=display_name, email=user_obj.email)
        db.add(m); db.commit(); db.refresh(m)
        print(f"  [OK] Miembro fondo: {display_name}")
    return m

fm_ana    = get_or_create_fund_member(ana,    "Ana García")
fm_carlos = get_or_create_fund_member(carlos, "Carlos García")
fm_lucia  = get_or_create_fund_member(lucia,  "Lucía García")

# Aportes mensuales: abril(~115d) mayo(~85d) junio(~55d) julio(~25d) agosto(~3d)
fund_contributions = [
    (fm_ana,    250_000, "Cuota abril",   ago(115)),
    (fm_carlos, 250_000, "Cuota abril",   ago(114)),
    (fm_lucia,  150_000, "Cuota abril",   ago(113)),
    (fm_ana,    250_000, "Cuota mayo",    ago(85)),
    (fm_carlos, 250_000, "Cuota mayo",    ago(84)),
    (fm_lucia,  150_000, "Cuota mayo",    ago(83)),
    (fm_ana,    250_000, "Cuota junio",   ago(55)),
    (fm_carlos, 250_000, "Cuota junio",   ago(54)),
    (fm_lucia,  150_000, "Cuota junio",   ago(53)),
    (fm_ana,    250_000, "Cuota julio",   ago(25)),
    (fm_carlos, 250_000, "Cuota julio",   ago(24)),
    (fm_lucia,  150_000, "Cuota julio",   ago(23)),
    (fm_ana,    250_000, "Cuota agosto",  ago(3)),
    (fm_carlos, 250_000, "Cuota agosto",  ago(4)),
    (fm_lucia,  150_000, "Cuota agosto",  ago(5)),
]

for member, amount, note, cdate in fund_contributions:
    exists = db.query(GroupFundContribution).filter(
        GroupFundContribution.group_id == fid,
        GroupFundContribution.member_id == member.id,
        GroupFundContribution.date == cdate,
    ).first()
    if not exists:
        db.add(GroupFundContribution(
            group_id=fid, member_id=member.id,
            amount=amount, note=note, date=cdate,
        ))
db.commit()
print("  [OK] Aportes del fondo creados")

# Gastos del fondo por mes
def add_fund_expense(description, amount, category, expense_date):
    existing = db.query(SharedExpense).filter(
        SharedExpense.group_id == fid,
        SharedExpense.description == description,
        SharedExpense.date == expense_date,
    ).first()
    if not existing:
        db.add(SharedExpense(
            group_id=fid, description=description, amount=amount,
            paid_by_id=fm_ana.id, category=category, date=expense_date,
        ))

fund_expenses = [
    # Abril
    ("Mercado del mes",         280_000, "Mercado",            ago(110)),
    ("Servicios públicos",      120_000, "Servicios públicos", ago(108)),
    ("Recarga gas domiciliario", 45_000, "Vivienda",           ago(105)),
    # Mayo
    ("Mercado del mes",         295_000, "Mercado",            ago(80)),
    ("Servicios públicos",      115_000, "Servicios públicos", ago(78)),
    ("Reparación plomería",      90_000, "Vivienda",           ago(72)),
    # Junio
    ("Mercado del mes",         310_000, "Mercado",            ago(50)),
    ("Servicios públicos",      118_000, "Servicios públicos", ago(48)),
    ("Útiles del hogar",         65_000, "Vivienda",           ago(44)),
    # Julio
    ("Mercado del mes",         270_000, "Mercado",            ago(20)),
    ("Servicios públicos",      122_000, "Servicios públicos", ago(18)),
    ("Mantenimiento jardín",     40_000, "Vivienda",           ago(15)),
    # Agosto
    ("Mercado del mes",         300_000, "Mercado",            ago(2)),
    ("Servicios públicos",      125_000, "Servicios públicos", ago(1)),
]

for desc, amt, cat, edate in fund_expenses:
    add_fund_expense(desc, amt, cat, edate)
db.commit()
print("  [OK] Gastos del fondo creados")

# ========================================================
# 7. ENTRENAR MODELOS PARA ANA
# ========================================================
print("\n-- Entrenando modelos ML de Ana ----------------------")
from models import Transaction as Tx
from services.ml_service import train_category_model, train_anomaly_model

all_txns = db.query(Tx).filter(Tx.user_id == ana.id).all()
metrics = train_category_model(ana.id, all_txns)
anom_ok = train_anomaly_model(ana.id, all_txns)

if metrics:
    print(f"  [OK] Regresión Logística entrenada")
    print(f"    Accuracy (CV-5) : {metrics['accuracy']:.1%}")
    print(f"    F1-weighted     : {metrics['f1_weighted']:.1%}")
    print(f"    Muestras        : {metrics['n_samples']}")
    print(f"    Categorías      : {metrics['n_categories']}")
else:
    print("  [!] Datos insuficientes para entrenar")

print(f"  {'[OK]' if anom_ok else '[!]'} Isolation Forest entrenado")

db.close()

# ========================================================
# RESUMEN
# ========================================================
print("""
==========================================================
  Seed completado [OK]
==========================================================

  Usuarios:
    demo@finsmart.co    /  demo1234   (Ana → usuario principal)
    carlos@finsmart.co  /  demo1234   (Carlos → pareja)
    lucia@finsmart.co   /  demo1234   (Lucía → hermana)

  Grupo familiar:  "Familia García"
  Miembros:        Ana · Carlos · Lucía · Papá (sin cuenta)

  Ana tiene:
    * ~160 gastos + 11 ingresos (6 meses de historia)
    * 4 anomalías plantadas para Isolation Forest
    * 6 presupuestos mensuales
    * 3 metas de ahorro con contribuciones
    * Gastos compartidos: mercado, arriendo, cine,
      paseos, regalos, mantenimiento carro
    * Splits: algunos saldados, otros pendientes

==========================================================
""")
