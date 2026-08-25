from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import User, Transaction, Budget
from services.email_service import send_budget_alert_email
from schemas import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    TransactionSummary,
    CategorySummary,
    MonthlyPoint,
    TrendResult,
)
from security import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import JWTError, jwt

router = APIRouter()


def _retrain_bg(user_id: int) -> None:
    from database import SessionLocal
    from services.ml_service import train_category_model, train_anomaly_model
    db = SessionLocal()
    try:
        txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
        train_category_model(user_id, txns)
        train_anomaly_model(user_id, txns)
    except Exception:
        pass
    finally:
        db.close()


def _check_budget_alert(db: Session, user: User, tx: Transaction, background_tasks: BackgroundTasks) -> None:
    """Avisa por correo cuando este gasto hace cruzar el 90% o el 100% del
    presupuesto de su categoría. Se compara el gasto acumulado del mes antes
    y después de esta transacción, así solo se manda el correo la vez que se
    cruza el umbral — no en cada transacción posterior que ya lo tenía superado."""
    budget = db.query(Budget).filter(
        Budget.user_id == user.id, Budget.category == tx.category
    ).first()
    if not budget or budget.limit_amount <= 0:
        return

    today = date.today()
    if tx.date.year != today.year or tx.date.month != today.month:
        return

    first_of_month = date(today.year, today.month, 1)
    spent_after = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.user_id == user.id,
        Transaction.category == tx.category,
        Transaction.type == "gasto",
        Transaction.date >= first_of_month,
        Transaction.date <= today,
    ).scalar()
    spent_before = spent_after - tx.amount
    limit = budget.limit_amount
    pct_before = spent_before / limit * 100
    pct_after = spent_after / limit * 100

    if pct_before < 100 <= pct_after:
        background_tasks.add_task(send_budget_alert_email, user.email, tx.category, spent_after, limit, True)
    elif pct_before < 90 <= pct_after:
        background_tasks.add_task(send_budget_alert_email, user.email, tx.category, spent_after, limit, False)


def _get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


@router.get("", response_model=List[TransactionResponse])
async def list_transactions(
    category: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if category:
        q = q.filter(Transaction.category == category)
    if type:
        q = q.filter(Transaction.type == type)
    if start_date:
        q = q.filter(Transaction.date >= start_date)
    if end_date:
        q = q.filter(Transaction.date <= end_date)
    return q.order_by(Transaction.date.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    tx = Transaction(**payload.model_dump(), user_id=current_user.id)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    background_tasks.add_task(_retrain_bg, current_user.id)
    if tx.type == "gasto":
        _check_budget_alert(db, current_user, tx, background_tasks)
    return tx


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    payload: TransactionUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id,
    ).first()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(tx, field, value)
    db.commit()
    db.refresh(tx)
    background_tasks.add_task(_retrain_bg, current_user.id)
    return tx


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id,
    ).first()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    db.delete(tx)
    db.commit()
    background_tasks.add_task(_retrain_bg, current_user.id)


@router.get("/summary", response_model=TransactionSummary)
async def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    today = date.today()
    first_of_month = date(today.year, today.month, 1)

    txs = db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= first_of_month,
        Transaction.date <= today,
    ).all()

    total_income = sum(t.amount for t in txs if t.type == "ingreso")
    total_expenses = sum(t.amount for t in txs if t.type == "gasto")
    balance = total_income - total_expenses

    category_map: dict[str, dict] = {}
    for t in txs:
        if t.type != "gasto":
            continue
        key = t.category
        if key not in category_map:
            category_map[key] = {"amount": 0.0, "count": 0}
        category_map[key]["amount"] += t.amount
        category_map[key]["count"] += 1

    by_category = [
        CategorySummary(category=cat, amount=data["amount"], count=data["count"])
        for cat, data in category_map.items()
    ]

    return TransactionSummary(
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance,
        by_category=by_category,
    )


MONTH_LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


@router.get("/monthly", response_model=List[MonthlyPoint])
async def get_monthly_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    from datetime import timedelta
    today = date.today()
    result = []
    for i in range(5, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)

        txs = db.query(Transaction).filter(
            Transaction.user_id == current_user.id,
            Transaction.date >= first_day,
            Transaction.date <= last_day,
        ).all()

        result.append(MonthlyPoint(
            month=f"{year}-{month:02d}",
            label=MONTH_LABELS[month - 1],
            income=sum(t.amount for t in txs if t.type == "ingreso"),
            expenses=sum(t.amount for t in txs if t.type == "gasto"),
        ))
    return result


@router.get("/trends", response_model=List[TrendResult])
async def get_trends(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    from services.ai_service import analyze_trends
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    return analyze_trends(transactions)


# ── ML endpoints ──────────────────────────────────────────────────────────────

@router.post("/ml/train", response_model=dict)
async def ml_train(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Entrena Random Forest (categorías) e Isolation Forest (anomalías) con los datos del usuario."""
    from services.ml_service import train_category_model, train_anomaly_model
    txns = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    cat_metrics = train_category_model(current_user.id, txns)
    anom_ok = train_anomaly_model(current_user.id, txns)
    if cat_metrics is None:
        raise HTTPException(
            status_code=400,
            detail=f"Datos insuficientes para entrenar (mínimo {10} transacciones en al menos 2 categorías).",
        )
    return {**cat_metrics, "anomaly_model_trained": anom_ok}


@router.get("/ml/suggest")
async def ml_suggest(
    description: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Predice la categoría para una descripción usando el modelo Random Forest del usuario."""
    from services.ml_service import predict_category, train_category_model
    result = predict_category(current_user.id, description)
    if result is None:
        # Intentar entrenar si aún no hay modelo
        txns = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
        train_category_model(current_user.id, txns)
        result = predict_category(current_user.id, description)
    return result or {"category": None, "confidence": 0, "alternatives": []}


@router.get("/ml/metrics", response_model=dict)
async def ml_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Retorna las métricas del modelo guardado. Solo re-entrena si no existe modelo."""
    from services.ml_service import _cat_path, _metrics_path, train_category_model
    import json, pickle

    mpath = _metrics_path(current_user.id)
    if mpath.exists():
        with open(mpath) as f:
            return json.load(f)

    # Primera vez — entrenar y guardar métricas
    txns = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    metrics = train_category_model(current_user.id, txns)
    return metrics or {"accuracy": None, "n_samples": 0, "message": "Datos insuficientes para entrenar el modelo."}


@router.get("/ml/compare", response_model=dict)
async def ml_compare(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Compara múltiples modelos de categorización y detección de anomalías con CV-5."""
    from services.ml_service import compare_category_models, compare_anomaly_models
    txns = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    cat_results  = compare_category_models(current_user.id, txns)
    anom_results = compare_anomaly_models(current_user.id, txns)
    return {
        "category_classification": cat_results or [],
        "anomaly_detection": anom_results or [],
    }


@router.get("/ml/anomalies", response_model=List[dict])
async def ml_anomalies(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Retorna el score de anomalía de cada transacción usando Isolation Forest."""
    from services.ml_service import score_anomalies, train_anomaly_model
    txns = db.query(Transaction).filter(Transaction.user_id == current_user.id).all()
    results = score_anomalies(current_user.id, txns)
    if not results:
        train_anomaly_model(current_user.id, txns)
        results = score_anomalies(current_user.id, txns)
    return results
