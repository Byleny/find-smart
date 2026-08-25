import os
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import engine, Base
import models
from routers import auth, transactions, budgets, saving_goals, shared, recurring, invoices, notifications

Base.metadata.create_all(bind=engine)

# Inline migrations for columns added after initial schema
with engine.connect() as _conn:
    from sqlalchemy import text as _text
    # Add columns if missing
    for _sql in [
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
        # Movistar: '1' = con número de línea, '2' = con referencia de pago
        "ALTER TABLE recurring_services ADD COLUMN payment_identifier TEXT",
        "ALTER TABLE shared_expense_splits ADD COLUMN settled_by_user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE saving_contributions ADD COLUMN date TEXT DEFAULT (date('now'))",
        "ALTER TABLE shared_groups ADD COLUMN group_type TEXT DEFAULT 'gastos'",
        "ALTER TABLE saving_goals ADD COLUMN current_amount REAL DEFAULT 0.0",
        "UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE saving_goals SET current_amount = 0.0 WHERE current_amount IS NULL",
        "UPDATE transactions SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE budgets SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE saving_goals SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE saving_contributions SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE shared_groups SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE shared_group_members SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE shared_expenses SET created_at = datetime('now') WHERE created_at IS NULL",
        "UPDATE recurring_services SET created_at = datetime('now') WHERE created_at IS NULL",
    ]:
        try:
            _conn.execute(_text(_sql))
            _conn.commit()
        except Exception:
            pass  # column already exists

    # Scrub email off inactive (departed/removed) membership rows so they can
    # never be silently re-linked, via the backfill below or a future
    # add_member call, to a different account that later registers under
    # that same address.
    try:
        _conn.execute(_text(
            "UPDATE shared_group_members SET email = NULL WHERE is_active = 0 AND email IS NOT NULL"
        ))
        _conn.commit()
    except Exception:
        pass

    # Backfill: link member records to users where email matches
    try:
        _conn.execute(_text("""
            UPDATE shared_group_members
            SET user_id = (
                SELECT id FROM users
                WHERE lower(users.email) = lower(shared_group_members.email)
                LIMIT 1
            )
            WHERE user_id IS NULL AND email IS NOT NULL
        """))
        _conn.commit()
    except Exception:
        pass

    # Cleanup: delete groups where all members are inactive
    try:
        _dead = _conn.execute(_text(
            "SELECT id FROM shared_groups WHERE id NOT IN "
            "(SELECT DISTINCT group_id FROM shared_group_members WHERE is_active = 1)"
        )).fetchall()
        for (_gid,) in _dead:
            _conn.execute(_text("DELETE FROM shared_expense_splits WHERE expense_id IN (SELECT id FROM shared_expenses WHERE group_id = :g)"), {"g": _gid})
            _conn.execute(_text("DELETE FROM shared_expenses WHERE group_id = :g"), {"g": _gid})
            _conn.execute(_text("DELETE FROM shared_group_members WHERE group_id = :g"), {"g": _gid})
            _conn.execute(_text("DELETE FROM shared_groups WHERE id = :g"), {"g": _gid})
        _conn.commit()
    except Exception:
        pass

app = FastAPI(title="FinSmart API", version="1.0.0")

# El navegador nunca llama al backend cruzando orígenes en el despliegue real
# (Next.js hace el proxy server-side vía rewrites), así que restringir esto
# no debería romper nada — pero "*" sí amplía la superficie si el JWT se
# filtrara por XSS: cualquier sitio podría llamar a la API con ese token.
# Configurable por si el dominio de despliegue cambia sin tocar código.
_cors_origins = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(transactions.router, prefix="/transactions", tags=["transactions"])
app.include_router(budgets.router, prefix="/budgets", tags=["budgets"])
app.include_router(saving_goals.router, prefix="/goals", tags=["goals"])
app.include_router(shared.router, prefix="/shared", tags=["shared"])
app.include_router(recurring.router, prefix="/recurring", tags=["recurring"])
app.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/")
def root():
    return {"message": "FinSmart API", "docs": "/docs"}
