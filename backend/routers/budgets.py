from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import User, Budget, Transaction
from schemas import BudgetCreate, BudgetUpdate, BudgetResponse
from security import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import JWTError, jwt

router = APIRouter()


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


def _calc_spent(db: Session, user_id: int, category: str) -> float:
    today = date.today()
    first_of_month = date(today.year, today.month, 1)
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.category == category,
        Transaction.type == "gasto",
        Transaction.date >= first_of_month,
        Transaction.date <= today,
    ).all()
    return sum(t.amount for t in txs)


@router.get("", response_model=List[BudgetResponse])
async def list_budgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()
    result = []
    for b in budgets:
        spent = _calc_spent(db, current_user.id, b.category)
        resp = BudgetResponse.model_validate(b)
        resp.spent_amount = spent
        result.append(resp)
    return result


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    budget = Budget(**payload.model_dump(), user_id=current_user.id)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    spent = _calc_spent(db, current_user.id, budget.category)
    resp = BudgetResponse.model_validate(budget)
    resp.spent_amount = spent
    return resp


@router.put("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    budget = db.query(Budget).filter(
        Budget.id == budget_id,
        Budget.user_id == current_user.id,
    ).first()
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(budget, field, value)
    db.commit()
    db.refresh(budget)
    spent = _calc_spent(db, current_user.id, budget.category)
    resp = BudgetResponse.model_validate(budget)
    resp.spent_amount = spent
    return resp


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    budget = db.query(Budget).filter(
        Budget.id == budget_id,
        Budget.user_id == current_user.id,
    ).first()
    if not budget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    db.delete(budget)
    db.commit()
