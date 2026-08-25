from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import get_db
from models import User, Transaction, Budget, SavingGoal, SavingContribution, RecurringService, Invoice, Notification
from schemas import Token, UserRegister, UserResponse, UserUpdate, AccountDeleteRequest
from security import (
    ACCESS_TOKEN_EXPIRE_DAYS,
    create_access_token,
    get_password_hash,
    verify_password,
    oauth2_scheme,
    SECRET_KEY,
    ALGORITHM,
)
from services.ml_service import delete_user_models
from routers.shared import leave_all_groups_for_user
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


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(_get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: AccountDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña incorrecta")

    user_id = current_user.id

    # Detach from every shared group first (transfers/deletes as needed, and
    # scrubs this account's email off any membership row so it can never be
    # silently re-linked to a future, different registration under the same
    # address).
    leave_all_groups_for_user(current_user, db)

    goal_ids = [g.id for g in db.query(SavingGoal).filter(SavingGoal.user_id == user_id).all()]
    if goal_ids:
        db.query(SavingContribution).filter(SavingContribution.goal_id.in_(goal_ids)).delete(synchronize_session=False)
        db.query(SavingGoal).filter(SavingGoal.id.in_(goal_ids)).delete(synchronize_session=False)

    service_ids = [s.id for s in db.query(RecurringService).filter(RecurringService.user_id == user_id).all()]
    if service_ids:
        db.query(Invoice).filter(Invoice.service_id.in_(service_ids)).delete(synchronize_session=False)
        db.query(RecurringService).filter(RecurringService.id.in_(service_ids)).delete(synchronize_session=False)

    db.query(Budget).filter(Budget.user_id == user_id).delete(synchronize_session=False)
    db.query(Transaction).filter(Transaction.user_id == user_id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)

    db.delete(current_user)
    db.commit()

    # Trained models are per-user files on disk — not covered by the DB
    # transaction above, so they're removed only once the delete is committed.
    delete_user_models(user_id)
