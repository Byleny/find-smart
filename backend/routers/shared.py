import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import text as _sql, func
from sqlalchemy.orm import Session

from database import get_db
from datetime import date as _date
from models import User, SharedGroup, SharedGroupMember, SharedExpense, SharedExpenseSplit, Transaction, GroupFundContribution, Notification
from services.email_service import send_group_invite_email, send_settle_request_email, cop as _cop
from schemas import (
    SharedGroupCreate,
    SharedGroupResponse,
    SharedGroupMemberCreate,
    SharedGroupMemberUpdate,
    SharedGroupMemberResponse,
    MemberAddResult,
    SharedExpenseCreate,
    SharedExpenseResponse,
    Balance,
    DebtItem,
    SettleSelectedSplitsPayload,
    SettleResult,
    FundContributionCreate,
    FundContributionResponse,
    FundStatus,
    FundMemberContrib,
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


def _can_access_group(group: SharedGroup, user_id: int, db: Session) -> bool:
    if group.creator_id == user_id:
        return True
    return db.query(SharedGroupMember).filter(
        SharedGroupMember.group_id == group.id,
        SharedGroupMember.user_id == user_id,
        SharedGroupMember.is_active == True,
    ).first() is not None


def _is_creator(group: SharedGroup, user_id: int) -> bool:
    return group.creator_id == user_id


@router.get("/groups", response_model=List[SharedGroupResponse])
async def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    creator_ids = {
        g.id for g in db.query(SharedGroup).filter(SharedGroup.creator_id == current_user.id).all()
    }
    linked_ids = {
        m.group_id for m in db.query(SharedGroupMember).filter(
            SharedGroupMember.user_id == current_user.id,
            SharedGroupMember.is_active == True,
        ).all()
    }
    all_ids = creator_ids | linked_ids
    if not all_ids:
        return []
    return db.query(SharedGroup).filter(SharedGroup.id.in_(all_ids)).all()


@router.post("/groups", response_model=SharedGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: SharedGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = SharedGroup(
        name=payload.name,
        description=payload.description,
        creator_id=current_user.id,
        group_type=payload.group_type,
    )
    db.add(group)
    db.flush()

    first_member = SharedGroupMember(
        group_id=group.id,
        name=payload.creator_name or current_user.full_name,
        email=payload.creator_email or current_user.email,
        user_id=current_user.id,
    )
    db.add(first_member)
    db.commit()
    db.refresh(group)
    return group


@router.get("/groups/{group_id}", response_model=SharedGroupResponse)
async def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return group


@router.post("/groups/{group_id}/members", response_model=MemberAddResult, status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: int,
    payload: SharedGroupMemberCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _is_creator(group, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el creador puede agregar miembros")

    existing = db.query(SharedGroupMember).filter(
        SharedGroupMember.group_id == group_id,
        SharedGroupMember.is_active == True,
        func.lower(SharedGroupMember.email) == payload.email.lower(),
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un miembro activo con ese correo en este grupo")

    linked_user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()

    # Si el correo pertenece a otra cuenta de FinSmart, se le envía una
    # invitación en vez de agregarla directo — solo queda vinculada al grupo
    # si la acepta desde sus notificaciones.
    if linked_user and linked_user.id != current_user.id:
        existing_invite = db.query(Notification).filter(
            Notification.user_id == linked_user.id,
            Notification.group_id == group_id,
            Notification.type == "group_invite",
            Notification.status == "pending",
        ).first()
        if existing_invite:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya hay una invitación pendiente para ese correo en este grupo")

        notif = Notification(
            user_id=linked_user.id,
            type="group_invite",
            title=f"{current_user.full_name} te invitó a \"{group.name}\"",
            body="Acepta para unirte al grupo y aparecer en sus gastos compartidos.",
            group_id=group_id,
            payload=json.dumps({
                "member_name": payload.name,
                "member_email": payload.email,
                "group_name": group.name,
                "inviter_name": current_user.full_name,
            }),
        )
        db.add(notif)
        db.commit()
        background_tasks.add_task(
            send_group_invite_email, linked_user.email, payload.name, group.name, current_user.full_name,
        )
        return MemberAddResult(
            status="invited",
            detail=f"Invitación enviada a {payload.email}. Se unirá al grupo cuando la acepte.",
            member=None,
        )

    member = SharedGroupMember(
        group_id=group_id,
        name=payload.name,
        email=payload.email,
        user_id=None,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return MemberAddResult(status="added", detail=f"{payload.name} agregado al grupo", member=member)


@router.put("/groups/{group_id}/members/{member_id}", response_model=SharedGroupMemberResponse)
async def update_member(
    group_id: int,
    member_id: int,
    payload: SharedGroupMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _is_creator(group, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el creador puede editar miembros")

    member = db.query(SharedGroupMember).filter(
        SharedGroupMember.id == member_id, SharedGroupMember.group_id == group_id
    ).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado")

    member.name = payload.name
    db.commit()
    db.refresh(member)
    return member


@router.delete("/groups/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _is_creator(group, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el creador puede eliminar miembros")

    member = db.query(SharedGroupMember).filter(
        SharedGroupMember.id == member_id, SharedGroupMember.group_id == group_id
    ).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado")
    if member.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes eliminarte a ti mismo. Usa 'Salir del grupo'.")

    if member.is_active:
        _deactivate_member(member)
        db.flush()
        _cleanup_group_if_empty(group_id, db)
        db.commit()
    return None


@router.post("/groups/{group_id}/expenses", response_model=SharedExpenseResponse, status_code=status.HTTP_201_CREATED)
async def add_expense(
    group_id: int,
    payload: SharedExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    is_fondo = getattr(group, "group_type", "gastos") == "fondo"

    if is_fondo:
        total_contributed = db.query(func.coalesce(func.sum(GroupFundContribution.amount), 0.0)).filter(
            GroupFundContribution.group_id == group_id
        ).scalar()
        total_spent = db.query(func.coalesce(func.sum(SharedExpense.amount), 0.0)).filter(
            SharedExpense.group_id == group_id
        ).scalar()
        available = round(total_contributed - total_spent, 2)
        if payload.amount > available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Saldo insuficiente en el fondo. Disponible: ${available:,.0f}, monto solicitado: ${payload.amount:,.0f}",
            )

    expense_data = payload.model_dump(exclude={"splits"})
    expense = SharedExpense(**expense_data, group_id=group_id)
    db.add(expense)
    db.flush()

    now = datetime.utcnow()

    if is_fondo:
        # Fondo groups: no splits, expense is paid from the communal pool.
        # The contributing transactions were already recorded at contribution time.
        pass
    elif payload.splits:
        for split_data in payload.splits:
            is_payer = split_data.member_id == payload.paid_by_id
            split = SharedExpenseSplit(
                expense_id=expense.id,
                member_id=split_data.member_id,
                amount=split_data.amount,
                is_settled=is_payer,
                settled_at=now if is_payer else None,
            )
            db.add(split)
    else:
        members = db.query(SharedGroupMember).filter(
            SharedGroupMember.group_id == group_id,
            SharedGroupMember.is_active == True,
        ).all()
        if members:
            per_person = round(payload.amount / len(members), 2)
            for member in members:
                is_payer = member.id == payload.paid_by_id
                split = SharedExpenseSplit(
                    expense_id=expense.id,
                    member_id=member.id,
                    amount=per_person,
                    is_settled=is_payer,
                    settled_at=now if is_payer else None,
                )
                db.add(split)

    if not is_fondo:
        # Register transaction for the payer if linked to a user account
        payer_member = db.query(SharedGroupMember).filter(SharedGroupMember.id == payload.paid_by_id).first()
        if payer_member and payer_member.user_id:
            txn = Transaction(
                user_id=payer_member.user_id,
                description=f"{expense.description} · {group.name}",
                amount=payload.amount,
                category="Gastos compartidos",
                type="gasto",
                date=expense.date,
            )
            db.add(txn)

    db.commit()
    db.refresh(expense)
    return expense


@router.get("/groups/{group_id}/balances", response_model=List[Balance])
async def get_balances(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    members = db.query(SharedGroupMember).filter(SharedGroupMember.group_id == group_id).all()
    member_map = {m.id: m for m in members}

    net: dict[int, float] = {m.id: 0.0 for m in members}

    # For each unsettled split: the payer is still owed that amount,
    # and the member still owes it. Settled splits are excluded because
    # they represent money already returned to the payer.
    expense_map = {
        e.id: e
        for e in db.query(SharedExpense).filter(SharedExpense.group_id == group_id).all()
    }
    splits = (
        db.query(SharedExpenseSplit)
        .join(SharedExpense)
        .filter(SharedExpense.group_id == group_id, SharedExpenseSplit.is_settled == False)
        .all()
    )
    for split in splits:
        expense = expense_map[split.expense_id]
        payer_id = expense.paid_by_id
        net[payer_id] = net.get(payer_id, 0.0) + split.amount
        net[split.member_id] = net.get(split.member_id, 0.0) - split.amount

    creditors = [(mid, bal) for mid, bal in net.items() if bal > 0]
    debtors = [(mid, -bal) for mid, bal in net.items() if bal < 0]
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    owes_to_map: dict[int, List[DebtItem]] = {m.id: [] for m in members}

    ci, di = 0, 0
    creditors_work = [list(c) for c in creditors]
    debtors_work = [list(d) for d in debtors]

    while ci < len(creditors_work) and di < len(debtors_work):
        cred_id, cred_bal = creditors_work[ci]
        debt_id, debt_bal = debtors_work[di]
        transfer = min(cred_bal, debt_bal)
        owes_to_map[debt_id].append(
            DebtItem(
                member_id=cred_id,
                member_name=member_map[cred_id].name,
                amount=round(transfer, 2),
            )
        )
        creditors_work[ci][1] -= transfer
        debtors_work[di][1] -= transfer
        if creditors_work[ci][1] < 0.01:
            ci += 1
        if debtors_work[di][1] < 0.01:
            di += 1

    result = []
    for m in members:
        result.append(
            Balance(
                member_id=m.id,
                member_name=m.name,
                net_balance=round(net[m.id], 2),
                owes_to=owes_to_map[m.id],
            )
        )
    return result


@router.put("/splits/{split_id}/settle", response_model=dict)
async def settle_split(
    split_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    split = db.query(SharedExpenseSplit).filter(SharedExpenseSplit.id == split_id).first()
    if not split:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split not found")

    expense = db.query(SharedExpense).filter(SharedExpense.id == split.expense_id).first()
    group = db.query(SharedGroup).filter(SharedGroup.id == expense.group_id).first()
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    split.is_settled = True
    split.settled_at = datetime.utcnow()
    split.settled_by_user_id = current_user.id
    db.commit()
    return {"detail": "Split marked as settled"}


def _settle_splits_now(splits: List[SharedExpenseSplit], db: Session, now: datetime) -> None:
    for s in splits:
        s.is_settled = True
        s.settled_at = now


def _request_or_settle(
    splits: List[SharedExpenseSplit],
    creditor_member: SharedGroupMember,
    debtor_user_id: int,
    debtor_name: str,
    obligations_str: str,
    db: Session,
    background_tasks: BackgroundTasks,
) -> SettleResult:
    """Si el acreedor tiene cuenta vinculada, crea una notificación para que él
    confirme el pago antes de saldar de verdad. Si no tiene cuenta (miembro
    sin registrar), no hay a quién pedirle confirmación — se salda de una vez,
    igual que antes."""
    now = datetime.utcnow()
    total = round(sum(s.amount for s in splits), 2)
    creditor_name = creditor_member.name if creditor_member else "compañero"

    if creditor_member and creditor_member.user_id and creditor_member.user_id != debtor_user_id:
        notif = Notification(
            user_id=creditor_member.user_id,
            type="settle_request",
            title=f"{debtor_name} dice que te pagó ${total:,.0f}",
            body=obligations_str,
            group_id=creditor_member.group_id,
            payload=json.dumps({
                "split_ids": [s.id for s in splits],
                "amount": total,
                "debtor_user_id": debtor_user_id,
                "debtor_name": debtor_name,
                "creditor_name": creditor_name,
                "obligations_str": obligations_str,
            }),
        )
        db.add(notif)
        db.commit()
        creditor_user = db.query(User).filter(User.id == creditor_member.user_id).first()
        if creditor_user:
            group = db.query(SharedGroup).filter(SharedGroup.id == creditor_member.group_id).first()
            background_tasks.add_task(
                send_settle_request_email,
                creditor_user.email, debtor_name, _cop(total),
                group.name if group else "", obligations_str,
            )
        return SettleResult(status="requested", detail=f"Se le pidió a {creditor_name} confirmar el pago", amount=total)

    _settle_splits_now(splits, db, now)
    db.add(Transaction(
        user_id=debtor_user_id,
        description=f"Pagué a {creditor_name}: {obligations_str}",
        amount=total,
        category="Gastos compartidos",
        type="gasto",
        date=now.date(),
    ))
    db.commit()
    return SettleResult(status="settled", detail=f"Saldado con {creditor_name}", amount=total)


@router.put("/groups/{group_id}/settle-between", response_model=SettleResult)
async def settle_between(
    group_id: int,
    debtor_id: int,
    creditor_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """El deudor marca como pagadas sus deudas con un acreedor. Si el
    acreedor tiene cuenta, queda pendiente de que él lo confirme."""
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    splits = (
        db.query(SharedExpenseSplit)
        .join(SharedExpense, SharedExpenseSplit.expense_id == SharedExpense.id)
        .filter(
            SharedExpense.group_id == group_id,
            SharedExpense.paid_by_id == creditor_id,
            SharedExpenseSplit.member_id == debtor_id,
            SharedExpenseSplit.is_settled == False,
        )
        .all()
    )
    if not splits:
        return SettleResult(status="settled", detail="No hay deudas pendientes", amount=0)

    expense_ids = list({s.expense_id for s in splits})
    expenses_settled = db.query(SharedExpense).filter(SharedExpense.id.in_(expense_ids)).all()
    expense_labels = [f"{e.description} (${e.amount:,.0f})" for e in expenses_settled[:3]]
    if len(expenses_settled) > 3:
        expense_labels.append(f"y {len(expenses_settled) - 3} más")
    obligations_str = ", ".join(expense_labels)

    creditor_member = db.query(SharedGroupMember).filter(SharedGroupMember.id == creditor_id).first()
    debtor_name = current_user.full_name or "compañero"

    return _request_or_settle(splits, creditor_member, current_user.id, debtor_name, obligations_str, db, background_tasks)


@router.post("/groups/{group_id}/settle-splits", response_model=SettleResult)
async def settle_selected_splits(
    group_id: int,
    payload: SettleSelectedSplitsPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """El deudor marca como pagado un subconjunto de splits elegido a mano.
    Si el acreedor tiene cuenta, queda pendiente de que él lo confirme."""
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=403, detail="Access denied")

    splits = db.query(SharedExpenseSplit).filter(
        SharedExpenseSplit.id.in_(payload.split_ids),
        SharedExpenseSplit.is_settled == False,
    ).all()
    if not splits:
        return SettleResult(status="settled", detail="No hay splits pendientes", amount=0)

    expense_ids = list({s.expense_id for s in splits})
    expenses_settled = db.query(SharedExpense).filter(SharedExpense.id.in_(expense_ids)).all()
    expense_labels = [f"{e.description} (${e.amount:,.0f})" for e in expenses_settled[:3]]
    if len(expenses_settled) > 3:
        expense_labels.append(f"y {len(expenses_settled) - 3} más")
    obligations_str = ", ".join(expense_labels)

    creditor_member = db.query(SharedGroupMember).filter(
        SharedGroupMember.id == payload.creditor_member_id
    ).first()
    debtor_name = current_user.full_name or "compañero"

    return _request_or_settle(splits, creditor_member, current_user.id, debtor_name, obligations_str, db, background_tasks)


@router.post("/groups/{group_id}/fund/contribute", response_model=FundContributionResponse, status_code=status.HTTP_201_CREATED)
async def contribute_to_fund(
    group_id: int,
    payload: FundContributionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=403, detail="Access denied")

    contrib_date = payload.date or _date.today()
    contrib = GroupFundContribution(
        group_id=group_id,
        member_id=payload.member_id,
        amount=payload.amount,
        note=payload.note,
        date=contrib_date,
    )
    db.add(contrib)

    # Register transaction for the contributing member if linked to a user account
    member = db.query(SharedGroupMember).filter(SharedGroupMember.id == payload.member_id).first()
    if member and member.user_id:
        note_suffix = f": {payload.note}" if payload.note else ""
        db.add(Transaction(
            user_id=member.user_id,
            description=f"Aporte al fondo {group.name}{note_suffix}",
            amount=payload.amount,
            category="Gastos compartidos",
            type="gasto",
            date=contrib_date,
        ))

    db.commit()
    db.refresh(contrib)
    return contrib


@router.get("/groups/{group_id}/fund", response_model=FundStatus)
async def get_fund_status(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=403, detail="Access denied")

    members = db.query(SharedGroupMember).filter(SharedGroupMember.group_id == group_id, SharedGroupMember.is_active == True).all()
    member_map = {m.id: m for m in members}

    contributions = (
        db.query(GroupFundContribution)
        .filter(GroupFundContribution.group_id == group_id)
        .order_by(GroupFundContribution.created_at.desc())
        .all()
    )
    expenses = db.query(SharedExpense).filter(SharedExpense.group_id == group_id).all()

    total_contributed = round(sum(c.amount for c in contributions), 2)
    total_spent = round(sum(e.amount for e in expenses), 2)

    per_member_map: dict[int, float] = {m.id: 0.0 for m in members}
    for c in contributions:
        if c.member_id in per_member_map:
            per_member_map[c.member_id] += c.amount

    per_member = [
        FundMemberContrib(
            member_id=mid,
            member_name=member_map[mid].name,
            total_contributed=round(total, 2),
        )
        for mid, total in per_member_map.items()
        if mid in member_map
    ]
    per_member.sort(key=lambda x: x.total_contributed, reverse=True)

    return FundStatus(
        total_contributed=total_contributed,
        total_spent=total_spent,
        balance=round(total_contributed - total_spent, 2),
        contributions=contributions,
        per_member=per_member,
    )


def _deactivate_member(member: SharedGroupMember) -> None:
    """Deactivate and unlink a member. Clears email too, so a stale row can
    never be silently re-linked (via the email-matching backfill or a future
    add_member call) to a different account that later registers with that
    same address."""
    member.is_active = False
    member.user_id = None
    member.email = None


def _cleanup_group_if_empty(group_id: int, db: Session) -> bool:
    """Delete group if no active members remain. Returns True if deleted."""
    active_count = db.query(SharedGroupMember).filter(
        SharedGroupMember.group_id == group_id,
        SharedGroupMember.is_active == True,
    ).count()
    if active_count == 0:
        db.execute(_sql("DELETE FROM shared_expense_splits WHERE expense_id IN (SELECT id FROM shared_expenses WHERE group_id = :g)"), {"g": group_id})
        db.execute(_sql("DELETE FROM shared_expenses WHERE group_id = :g"), {"g": group_id})
        db.execute(_sql("DELETE FROM shared_group_members WHERE group_id = :g"), {"g": group_id})
        db.execute(_sql("DELETE FROM shared_groups WHERE id = :g"), {"g": group_id})
        return True
    return False


@router.delete("/groups/{group_id}/leave", status_code=204)
async def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    all_members = db.query(SharedGroupMember).filter(SharedGroupMember.group_id == group_id).all()

    # Find member — active or already inactive (handles retries after partial failures)
    member = next((m for m in all_members if m.user_id == current_user.id), None)
    if not member:
        member = next((m for m in all_members if m.email and m.email.lower() == current_user.email.lower()), None)

    if member and member.is_active:
        _deactivate_member(member)

        # Transfer creator role if needed
        active_others = [m for m in all_members if m.id != member.id and m.is_active and m.user_id is not None]
        if group.creator_id == current_user.id and active_others:
            group.creator_id = active_others[0].user_id

        db.flush()

    elif not member:
        raise HTTPException(status_code=404, detail="No eres miembro de este grupo")
    # else: member already inactive — still run cleanup below

    _cleanup_group_if_empty(group_id, db)
    db.commit()


def leave_all_groups_for_user(user: User, db: Session) -> None:
    """Detach a user from every shared group they belong to — same effect as
    calling leave_group() on each one. Used when an account is deleted, so no
    shared-group membership (and no trace of its email) survives the account
    that owned it."""
    member_rows = db.query(SharedGroupMember).filter(
        SharedGroupMember.user_id == user.id,
        SharedGroupMember.is_active == True,
    ).all()
    for member in member_rows:
        group = db.query(SharedGroup).filter(SharedGroup.id == member.group_id).first()
        if not group:
            continue
        _deactivate_member(member)
        active_others = db.query(SharedGroupMember).filter(
            SharedGroupMember.group_id == group.id,
            SharedGroupMember.id != member.id,
            SharedGroupMember.is_active == True,
            SharedGroupMember.user_id.isnot(None),
        ).all()
        if group.creator_id == user.id and active_others:
            group.creator_id = active_others[0].user_id
        db.flush()
        _cleanup_group_if_empty(group.id, db)
