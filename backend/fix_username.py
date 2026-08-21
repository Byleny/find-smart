from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("UPDATE users SET full_name = 'Ana García' WHERE email = 'demo@finsmart.co'"))
db.commit()
print("Ana García updated")
db.close()
