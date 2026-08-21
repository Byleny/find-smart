"""
Elimina todas las transacciones personales de Ana y re-ejecuta el seed limpio.
Seguro porque demo@finsmart.co es una cuenta de prueba.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text
from database import SessionLocal
from models import User, Transaction

db = SessionLocal()
ana = db.query(User).filter(User.email == "demo@finsmart.co").first()
if not ana:
    print("[ERROR] Usuario demo@finsmart.co no encontrado")
    db.close()
    sys.exit(1)

count = db.query(Transaction).filter(Transaction.user_id == ana.id).count()
print(f"Eliminando {count} transacciones de Ana (id={ana.id})...")
db.query(Transaction).filter(Transaction.user_id == ana.id).delete()
db.commit()
print(f"[OK] Transacciones eliminadas. Ana queda con {db.query(Transaction).filter(Transaction.user_id == ana.id).count()} transacciones.")
db.close()
