from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import User, SavingGoal, SavingContribution, Transaction
from schemas import (
    SavingGoalCreate,
    SavingGoalUpdate,
    SavingGoalResponse,
    SavingContributionCreate,
    SavingContributionResponse,
)
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


@router.get("", response_model=List[SavingGoalResponse])
async def list_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    return db.query(SavingGoal).filter(SavingGoal.user_id == current_user.id).all()


@router.post("", response_model=SavingGoalResponse, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: SavingGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    goal = SavingGoal(**payload.model_dump(), user_id=current_user.id)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


@router.put("/{goal_id}", response_model=SavingGoalResponse)
async def update_goal(
    goal_id: int,
    payload: SavingGoalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    goal = db.query(SavingGoal).filter(
        SavingGoal.id == goal_id,
        SavingGoal.user_id == current_user.id,
    ).first()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    goal = db.query(SavingGoal).filter(
        SavingGoal.id == goal_id,
        SavingGoal.user_id == current_user.id,
    ).first()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    db.delete(goal)
    db.commit()


@router.post("/{goal_id}/contribute", response_model=SavingContributionResponse, status_code=status.HTTP_201_CREATED)
async def contribute(
    goal_id: int,
    payload: SavingContributionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    goal = db.query(SavingGoal).filter(
        SavingGoal.id == goal_id,
        SavingGoal.user_id == current_user.id,
    ).first()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")

    from datetime import date as _date
    contrib_data = payload.model_dump()
    if not contrib_data.get("date"):
        contrib_data["date"] = _date.today()

    contribution = SavingContribution(**contrib_data, goal_id=goal.id)
    db.add(contribution)
    goal.current_amount += payload.amount

    # Registrar como transacción para reflejar en saldo y análisis
    db.add(Transaction(
        user_id=current_user.id,
        description=f"Aporte meta: {goal.name}",
        amount=payload.amount,
        category="Ahorro",
        type="gasto",
        date=contrib_data["date"],
    ))

    db.commit()
    db.refresh(contribution)
    return contribution


@router.get("/{goal_id}/contributions", response_model=List[SavingContributionResponse])
async def list_contributions(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    goal = db.query(SavingGoal).filter(
        SavingGoal.id == goal_id,
        SavingGoal.user_id == current_user.id,
    ).first()
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found")
    return (
        db.query(SavingContribution)
        .filter(SavingContribution.goal_id == goal_id)
        .order_by(SavingContribution.date.desc())
        .all()
    )
