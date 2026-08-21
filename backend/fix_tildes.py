"""
Corrige los caracteres acentuados corruptos (guardados como '?') en la base de datos.
Ejecutar con: python fix_tildes.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text
from database import SessionLocal

db = SessionLocal()

def fix(table, col, old, new, extra_where=""):
    sql = f"UPDATE {table} SET {col} = :new WHERE {col} = :old{extra_where}"
    r = db.execute(text(sql), {"new": new, "old": old})
    if r.rowcount:
        print(f"  [OK] {table}.{col}: '{old}' → '{new}' ({r.rowcount} fila(s))")

print("\n-- Corrigiendo transacciones.description --")
desc_fixes = [
    ("Supermercado ?xito",            "Supermercado Éxito"),
    ("Pan y caf?",                     "Pan y café"),
    ("Cafeter?a oficina",              "Cafetería oficina"),
    ("Gasolina veh?culo",             "Gasolina vehículo"),
    ("Energ?a Enel",                  "Energía Enel"),
    ("Droguer?a Cruz Verde",          "Droguería Cruz Verde"),
    ("Droguer?a La Rebaja",           "Droguería La Rebaja"),
    ("M?dico particular",             "Médico particular"),
    ("Administraci?n",                "Administración"),
    ("Reparaci?n plomer?a",           "Reparación plomería"),
    ("Pintura habitaci?n",            "Pintura habitación"),
    ("Art?culos hogar",               "Artículos hogar"),
    ("Juego en l?nea",                "Juego en línea"),
    ("Odont?logo",                    "Odontólogo"),
    ("Laboratorio cl?nico",           "Laboratorio clínico"),
    ("Freelance dise?o",              "Freelance diseño"),
    ("Bonificaci?n",                  "Bonificación"),
]
for old, new in desc_fixes:
    fix("transactions", "description", old, new)

print("\n-- Corrigiendo transacciones.category --")
fix("transactions", "category", "Alimentaci?n", "Alimentación")

print("\n-- Corrigiendo presupuestos.category --")
fix("budgets", "category", "Alimentaci?n", "Alimentación")

print("\n-- Corrigiendo usuarios.full_name --")
user_fixes = [
    ("Ana Garc?a",    "Ana García"),
    ("Carlos Garc?a", "Carlos García"),
    ("Luc?a Garc?a",  "Lucía García"),
]
for old, new in user_fixes:
    fix("users", "full_name", old, new)

print("\n-- Corrigiendo miembros del grupo --")
member_fixes = [
    ("Ana Garc?a",    "Ana García"),
    ("Carlos Garc?a", "Carlos García"),
    ("Luc?a Garc?a",  "Lucía García"),
    ("Pap?",          "Papá"),
]
for old, new in member_fixes:
    fix("shared_group_members", "name", old, new)

print("\n-- Corrigiendo nombre del grupo --")
fix("shared_groups", "name", "Familia Garc?a", "Familia García")

print("\n-- Corrigiendo gastos compartidos --")
shared_fixes = [
    ("Mercado familiar ? Mercado enero",      "Mercado familiar · Mercado enero"),
    ("Mercado familiar ? Mercado diciembre",  "Mercado familiar · Mercado diciembre"),
    ("Mercado familiar ? Mercado noviembre",  "Mercado familiar · Mercado noviembre"),
    ("Mercado familiar ? Mercado octubre",    "Mercado familiar · Mercado octubre"),
    ("Cena cumplea?os pap?",                  "Cena cumpleaños papá"),
    ("Cine Colombia ? funci?n familiar",      "Cine Colombia · función familiar"),
]
for old, new in shared_fixes:
    fix("shared_expenses", "description", old, new)

fix("shared_expenses", "category", "Alimentaci?n", "Alimentación")

print("\n-- Corrigiendo metas de ahorro --")
fix("saving_goals", "description", "3 meses de gastos como colch?n financiero",
    "3 meses de gastos como colchón financiero")

db.commit()
db.close()
print("\n[OK] Corrección de tildes completada.\n")
