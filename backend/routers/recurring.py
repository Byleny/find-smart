from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import User, RecurringService, Invoice, Transaction
from schemas import (
    RecurringServiceCreate,
    RecurringServiceUpdate,
    RecurringServiceResponse,
    InvoiceResult,
    PatternResult,
)
from security import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import JWTError, jwt
from services.scraper_service import fetch_invoice as scraper_fetch
from services.qr_service import generate_payment_qr
from services.ai_service import detect_patterns, predict_next_payment

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


@router.get("", response_model=List[RecurringServiceResponse])
async def list_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    return (
        db.query(RecurringService)
        .filter(
            RecurringService.user_id == current_user.id,
            RecurringService.is_active == True,
        )
        .all()
    )


@router.post("", response_model=RecurringServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: RecurringServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    service = RecurringService(**payload.model_dump(), user_id=current_user.id)
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.put("/{service_id}", response_model=RecurringServiceResponse)
async def update_service(
    service_id: int,
    payload: RecurringServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    service = db.query(RecurringService).filter(
        RecurringService.id == service_id,
        RecurringService.user_id == current_user.id,
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    service = db.query(RecurringService).filter(
        RecurringService.id == service_id,
        RecurringService.user_id == current_user.id,
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    service.is_active = False
    db.commit()


@router.post("/{service_id}/fetch-invoice", response_model=InvoiceResult)
async def fetch_invoice_endpoint(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    service = db.query(RecurringService).filter(
        RecurringService.id == service_id,
        RecurringService.user_id == current_user.id,
        RecurringService.is_active == True,
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    try:
        result = scraper_fetch(service.provider, service.account_reference)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch invoice: {exc}",
        )

    qr_base64 = generate_payment_qr(
        service_name=service.name,
        provider=service.provider,
        reference=result.reference,
        amount=result.amount,
        due_date=str(result.due_date),
    )

    invoice = Invoice(
        service_id=service.id,
        amount=result.amount,
        due_date=result.due_date,
        qr_data=qr_base64,
    )
    db.add(invoice)

    service.last_fetched_amount = result.amount
    service.last_fetched_at = datetime.utcnow()
    db.commit()

    return InvoiceResult(
        amount=result.amount,
        due_date=result.due_date,
        reference=result.reference,
        qr_base64=qr_base64,
        service_name=service.name,
    )


@router.get("/patterns", response_model=List[PatternResult])
async def get_patterns(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .all()
    )
    return detect_patterns(transactions)


@router.get("/{service_id}/predict", response_model=dict)
async def predict_payment(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    service = db.query(RecurringService).filter(
        RecurringService.id == service_id,
        RecurringService.user_id == current_user.id,
    ).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    invoices = (
        db.query(Invoice)
        .filter(Invoice.service_id == service_id)
        .order_by(Invoice.due_date.asc())
        .all()
    )
    prediction = predict_next_payment(service, invoices)
    return prediction
