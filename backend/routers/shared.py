from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text as _sql
from sqlalchemy.orm import Session

from database import get_db
from datetime import date as _date
from models import User, SharedGroup, SharedGroupMember, SharedExpense, SharedExpenseSplit, Transaction, GroupFundContribution
from schemas import (
    SharedGroupCreate,
    SharedGroupResponse,
    SharedGroupMemberCreate,
    SharedGroupMemberResponse,
    SharedExpenseCreate,
    SharedExpenseResponse,
    Balance,
    DebtItem,
    SettleSelectedSplitsPayload,
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


@router.post("/groups/{group_id}/members", response_model=SharedGroupMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: int,
    payload: SharedGroupMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _is_creator(group, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo el creador puede agregar miembros")

    linked_user = None
    if payload.email:
        linked_user = db.query(User).filter(User.email == payload.email.lower()).first()

    member = SharedGroupMember(
        group_id=group_id,
        name=payload.name,
        email=payload.email,
        user_id=linked_user.id if linked_user else None,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


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

    expense_data = payload.model_dump(exclude={"splits"})
    expense = SharedExpense(**expense_data, group_id=group_id)
    db.add(expense)
    db.flush()

    now = datetime.utcnow()
    is_fondo = getattr(group, "group_type", "gastos") == "fondo"

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
        members = db.query(SharedGroupMember).filter(SharedGroupMember.group_id == group_id).all()
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
    db.commit()
    return {"detail": "Split marked as settled"}


@router.put("/groups/{group_id}/settle-between", response_model=dict)
async def settle_between(
    group_id: int,
    debtor_id: int,
    creditor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Mark all unsettled splits of debtor_id that belong to expenses paid by creditor_id."""
    group = db.query(SharedGroup).filter(SharedGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if not _can_access_group(group, current_user.id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.utcnow()
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
    total = round(sum(s.amount for s in splits), 2)

    # Collect expense names before marking settled
    expense_ids = list({s.expense_id for s in splits})
    expenses_settled = db.query(SharedExpense).filter(SharedExpense.id.in_(expense_ids)).all()
    expense_labels = [f"{e.description} (${e.amount:,.0f})" for e in expenses_settled[:3]]
    if len(expenses_settled) > 3:
        expense_labels.append(f"y {len(expenses_settled) - 3} más")
    obligations_str = ", ".join(expense_labels)

    for s in splits:
        s.is_settled = True
        s.settled_at = now

    creditor_member = db.query(SharedGroupMember).filter(SharedGroupMember.id == creditor_id).first()
    debtor_member = db.query(SharedGroupMember).filter(SharedGroupMember.id == debtor_id).first()

    if total > 0:
        creditor_name = creditor_member.name if creditor_member else "compañero"
        debtor_name = debtor_member.name if debtor_member else "compañero"

        # Gasto para quien paga (siempre el usuario activo)
        db.add(Transaction(
            user_id=current_user.id,
            description=f"Pagué a {creditor_name}: {obligations_str}",
            amount=total,
            category="Gastos compartidos",
            type="gasto",
            date=now.date(),
        ))

        # Ingreso para el acreedor si tiene cuenta vinculada
        if creditor_member and creditor_member.user_id and creditor_member.user_id != current_user.id:
            db.add(Transaction(
                user_id=creditor_member.user_id,
                description=f"{debtor_name} me pagó: {obligations_str}",
                amount=total,
                category="Gastos compartidos",
                type="ingreso",
                date=now.date(),
            ))

    db.commit()
    return {"detail": f"Settled {len(splits)} split(s)", "amount": total}


@router.post("/groups/{group_id}/settle-splits", response_model=dict)
async def settle_selected_splits(
    group_id: int,
    payload: SettleSelectedSplitsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    """Settle a user-selected subset of splits and record a transaction for the total."""
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
        return {"detail": "No unsettled splits found", "amount": 0}

    now = datetime.utcnow()
    total = round(sum(s.amount for s in splits), 2)

    expense_ids = list({s.expense_id for s in splits})
    expenses_settled = db.query(SharedExpense).filter(SharedExpense.id.in_(expense_ids)).all()
    expense_labels = [f"{e.description} (${e.amount:,.0f})" for e in expenses_settled[:3]]
    if len(expenses_settled) > 3:
        expense_labels.append(f"y {len(expenses_settled) - 3} más")
    obligations_str = ", ".join(expense_labels)

    for s in splits:
        s.is_settled = True
        s.settled_at = now

    creditor_member = db.query(SharedGroupMember).filter(
        SharedGroupMember.id == payload.creditor_member_id
    ).first()
    creditor_name = creditor_member.name if creditor_member else "compañero"

    db.add(Transaction(
        user_id=current_user.id,
        description=f"Pagué a {creditor_name}: {obligations_str}",
        amount=total,
        category="Gastos compartidos",
        type="gasto",
        date=now.date(),
    ))

    if creditor_member and creditor_member.user_id and creditor_member.user_id != current_user.id:
        debtor_name = current_user.full_name or "compañero"
        db.add(Transaction(
            user_id=creditor_member.user_id,
            description=f"{debtor_name} me pagó: {obligations_str}",
            amount=total,
            category="Gastos compartidos",
            type="ingreso",
            date=now.date(),
        ))

    db.commit()
    return {"detail": f"Settled {len(splits)} split(s)", "amount": total}


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
        # Mark as inactive and unlink
        member.is_active = False
        member.user_id = None

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
