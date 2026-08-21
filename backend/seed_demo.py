"""
Script de datos de demostración — FinSmart
Crea un usuario demo con 4 meses de transacciones realistas (Colombia/Cali)
diseñadas para que los tres modelos ML sean claramente visibles:
  · Random Forest   → sugiere categorías (dataset variado, accuracy ~88-93%)
  · Isolation Forest → marca los gastos inusuales
  · DBSCAN          → detecta patrones recurrentes
"""

from datetime import date, timedelta
from database import SessionLocal
from models import User, Transaction
from security import get_password_hash

db = SessionLocal()

# ── Usuario demo ──────────────────────────────────────────────────────────────
existing = db.query(User).filter(User.email == "demo@finsmart.co").first()
if existing:
    user = existing
    print(f"Usuario ya existe → id={user.id}")
else:
    user = User(
        email="demo@finsmart.co",
        hashed_password=get_password_hash("demo1234"),
        full_name="Ana García",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Usuario creado → id={user.id}  |  email: demo@finsmart.co  |  clave: demo1234")

uid = user.id

# ── Transacciones (120 días de historia) ─────────────────────────────────────
today = date.today()

def ago(days): return today - timedelta(days=days)

# Formato: (descripción, monto, categoría, fecha)
gastos = [
    # ── ALIMENTACIÓN — marcas claras ──
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

    # ── TRANSPORTE — variado ──
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

    # ── SERVICIOS ──
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
    ("Energía Enel",              55_000, "Servicios", ago(8)),
    ("Energía Enel",              58_000, "Servicios", ago(38)),
    ("Plan celular Claro",        39_900, "Servicios", ago(3)),
    ("Plan celular Claro",        39_900, "Servicios", ago(33)),

    # ── ENTRETENIMIENTO ──
    ("Netflix",                   22_900, "Entretenimiento", ago(3)),
    ("Netflix",                   22_900, "Entretenimiento", ago(33)),
    ("Netflix",                   22_900, "Entretenimiento", ago(63)),
    ("Netflix",                   22_900, "Entretenimiento", ago(93)),
    ("Spotify",                   10_900, "Entretenimiento", ago(6)),
    ("Spotify",                   10_900, "Entretenimiento", ago(36)),
    ("Spotify",                   10_900, "Entretenimiento", ago(66)),
    ("Cine Colombia",             19_000, "Entretenimiento", ago(14)),
    ("Cine Colombia",             21_000, "Entretenimiento", ago(44)),
    ("Cinemark",                  18_500, "Entretenimiento", ago(28)),
    ("Juego en línea",            15_000, "Entretenimiento", ago(20)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(7)),
    ("Disney Plus",               19_900, "Entretenimiento", ago(37)),
    ("Concierto",                 85_000, "Entretenimiento", ago(50)),

    # ── SALUD ──
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

    # ── VIVIENDA ──
    ("Arriendo apartamento",     900_000, "Vivienda", ago(5)),
    ("Arriendo apartamento",     900_000, "Vivienda", ago(35)),
    ("Arriendo apartamento",     900_000, "Vivienda", ago(65)),
    ("Arriendo apartamento",     900_000, "Vivienda", ago(95)),
    ("Administración",            95_000, "Vivienda", ago(8)),
    ("Administración",            95_000, "Vivienda", ago(38)),
    ("Administración",            95_000, "Vivienda", ago(68)),
    ("Reparación plomería",       80_000, "Vivienda", ago(22)),
    ("Pintura habitación",       150_000, "Vivienda", ago(60)),
    ("Artículos hogar",           45_000, "Vivienda", ago(17)),

    # ── ANOMALÍAS plantadas (Isolation Forest las detecta) ──
    ("Supermercado Éxito",       520_000, "Alimentación",    ago(16)),  # 13× normal ⚠️
    ("Uber",                     180_000, "Transporte",      ago(9)),   # 13× normal ⚠️
    ("Cine Colombia",            350_000, "Entretenimiento", ago(21)),  # evento especial ⚠️
    ("Droguería Cruz Verde",     280_000, "Salud",           ago(55)),  # cirugía ⚠️
]

ingresos = [
    ("Salario octubre",    3_200_000, "Salario",   ago(115)),
    ("Salario noviembre",  3_200_000, "Salario",   ago(85)),
    ("Salario diciembre",  3_200_000, "Salario",   ago(55)),
    ("Salario enero",      3_350_000, "Salario",   ago(25)),
    ("Freelance diseño",     450_000, "Freelance", ago(45)),
    ("Freelance video",      320_000, "Freelance", ago(70)),
    ("Venta celular usado",  380_000, "Ventas",    ago(30)),
    ("Bonificación",         500_000, "Salario",   ago(20)),
]

# ── Insertar sin duplicados ───────────────────────────────────────────────────
existing_keys = {
    (t.description, str(t.date))
    for t in db.query(Transaction).filter(Transaction.user_id == uid).all()
}

added = 0
for desc, amount, cat, tdate in gastos:
    if (desc, str(tdate)) not in existing_keys:
        db.add(Transaction(
            user_id=uid, description=desc, amount=amount,
            category=cat, type="gasto", date=tdate,
        ))
        added += 1

for desc, amount, cat, tdate in ingresos:
    if (desc, str(tdate)) not in existing_keys:
        db.add(Transaction(
            user_id=uid, description=desc, amount=amount,
            category=cat, type="ingreso", date=tdate,
        ))
        added += 1

db.commit()
print(f"\n✓ {added} transacciones agregadas al usuario id={uid}")

# ── Entrenar modelos automáticamente ─────────────────────────────────────────
print("\nEntrenando modelos ML con los datos semilla...")
from models import Transaction as Tx
from services.ml_service import train_category_model, train_anomaly_model
import json

all_txns = db.query(Tx).filter(Tx.user_id == uid).all()
metrics = train_category_model(uid, all_txns)
anom_ok = train_anomaly_model(uid, all_txns)

if metrics:
    print(f"✓ Random Forest entrenado")
    print(f"  Accuracy (CV-5):   {metrics['accuracy']:.1%}")
    print(f"  F1-weighted:       {metrics['f1_weighted']:.1%}")
    print(f"  Muestras:          {metrics['n_samples']}")
    print(f"  Categorías:        {metrics['n_categories']}")
else:
    print("✗ Datos insuficientes para Random Forest")

print(f"{'✓' if anom_ok else '✗'} Isolation Forest entrenado")

db.close()
print("\nCredenciales de acceso:")
print("  Email : demo@finsmart.co")
print("  Clave : demo1234")
