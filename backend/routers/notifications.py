import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import User, Notification, SharedGroup, SharedGroupMember, SharedExpenseSplit, Transaction
from schemas import NotificationResponse
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


@router.get("", response_model=List[NotificationResponse])
async def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )


def _get_pending_notification(notification_id: int, db: Session, current_user: User) -> Notification:
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificación no encontrada")
    if notif.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta notificación ya fue resuelta")
    return notif


@router.post("/{notification_id}/accept", response_model=dict)
async def accept_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    notif = _get_pending_notification(notification_id, db, current_user)
    data = json.loads(notif.payload or "{}")

    if notif.type == "group_invite":
        group = db.query(SharedGroup).filter(SharedGroup.id == notif.group_id).first()
        if not group:
            notif.status = "rejected"
            notif.resolved_at = datetime.utcnow()
            db.commit()
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El grupo ya no existe")

        already = db.query(SharedGroupMember).filter(
            SharedGroupMember.group_id == notif.group_id,
            SharedGroupMember.user_id == current_user.id,
            SharedGroupMember.is_active == True,
        ).first()
        if not already:
            db.add(SharedGroupMember(
                group_id=notif.group_id,
                name=data.get("member_name") or current_user.full_name,
                email=data.get("member_email") or current_user.email,
                user_id=current_user.id,
            ))

    elif notif.type == "settle_request":
        splits = db.query(SharedExpenseSplit).filter(
            SharedExpenseSplit.id.in_(data.get("split_ids", [])),
            SharedExpenseSplit.is_settled == False,
        ).all()
        now = datetime.utcnow()
        total = round(sum(s.amount for s in splits), 2)
        for s in splits:
            s.is_settled = True
            s.settled_at = now
        if total > 0:
            debtor_user_id = data.get("debtor_user_id")
            creditor_name = data.get("creditor_name", "compañero")
            obligations_str = data.get("obligations_str", "")
            if debtor_user_id:
                db.add(Transaction(
                    user_id=debtor_user_id,
                    description=f"Pagué a {creditor_name}: {obligations_str}",
                    amount=total,
                    category="Gastos compartidos",
                    type="gasto",
                    date=now.date(),
                ))
            db.add(Transaction(
                user_id=current_user.id,
                description=f"{data.get('debtor_name', 'Un compañero')} me pagó: {obligations_str}",
                amount=total,
                category="Gastos compartidos",
                type="ingreso",
                date=now.date(),
            ))

    notif.status = "accepted"
    notif.resolved_at = datetime.utcnow()
    db.commit()
    return {"detail": "Aceptado"}


@router.post("/{notification_id}/reject", response_model=dict)
async def reject_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    notif = _get_pending_notification(notification_id, db, current_user)
    notif.status = "rejected"
    notif.resolved_at = datetime.utcnow()
    db.commit()
    return {"detail": "Rechazado"}
