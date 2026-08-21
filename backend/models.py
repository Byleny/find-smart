from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    ForeignKey, Text
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    identification_type = Column(String, nullable=True, default="CC")
    identification_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user")
    budgets = relationship("Budget", back_populates="user")
    saving_goals = relationship("SavingGoal", back_populates="user")
    recurring_services = relationship("RecurringService", back_populates="user")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    type = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)
    limit_amount = Column(Float, nullable=False)
    period = Column(String, default="monthly")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="budgets")


class SavingGoal(Base):
    __tablename__ = "saving_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0.0)
    deadline = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="saving_goals")
    contributions = relationship(
        "SavingContribution", back_populates="goal", cascade="all, delete-orphan"
    )


class SavingContribution(Base):
    __tablename__ = "saving_contributions"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("saving_goals.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    goal = relationship("SavingGoal", back_populates="contributions")


class SharedGroup(Base):
    __tablename__ = "shared_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    group_type = Column(String, default="gastos", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship(
        "SharedGroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    expenses = relationship(
        "SharedExpense", back_populates="group", cascade="all, delete-orphan"
    )
    fund_contributions = relationship(
        "GroupFundContribution", back_populates="group", cascade="all, delete-orphan"
    )


class SharedGroupMember(Base):
    __tablename__ = "shared_group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("shared_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("SharedGroup", back_populates="members")
    linked_user = relationship("User")
    paid_expenses = relationship("SharedExpense", back_populates="paid_by")
    splits = relationship(
        "SharedExpenseSplit", back_populates="member", cascade="all, delete-orphan"
    )


class SharedExpense(Base):
    __tablename__ = "shared_expenses"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("shared_groups.id", ondelete="CASCADE"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    paid_by_id = Column(Integer, ForeignKey("shared_group_members.id"), nullable=False)
    category = Column(String, nullable=True)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("SharedGroup", back_populates="expenses")
    paid_by = relationship("SharedGroupMember", back_populates="paid_expenses")
    splits = relationship(
        "SharedExpenseSplit", back_populates="expense", cascade="all, delete-orphan"
    )


class SharedExpenseSplit(Base):
    __tablename__ = "shared_expense_splits"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("shared_expenses.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("shared_group_members.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    is_settled = Column(Boolean, default=False)
    settled_at = Column(DateTime, nullable=True)

    expense = relationship("SharedExpense", back_populates="splits")
    member = relationship("SharedGroupMember", back_populates="splits")


class GroupFundContribution(Base):
    __tablename__ = "group_fund_contributions"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("shared_groups.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("shared_group_members.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(String, nullable=True)
    date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("SharedGroup", back_populates="fund_contributions")
    member = relationship("SharedGroupMember")


class RecurringService(Base):
    __tablename__ = "recurring_services"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    account_reference = Column(String, nullable=False)
    category = Column(String, nullable=False)
    estimated_amount = Column(Float, nullable=False)
    billing_day = Column(Integer, nullable=False)
    last_fetched_amount = Column(Float, nullable=True)
    last_fetched_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Datos del pagador específicos para este contrato (sobreescribe perfil de usuario)
    payer_name = Column(String, nullable=True)
    payer_id_type = Column(String, nullable=True)
    payer_id_number = Column(String, nullable=True)
    payer_phone = Column(String, nullable=True)
    payer_email = Column(String, nullable=True)
    # Movistar: cómo se identifica el pago — '1' número de línea, '2' referencia de pago
    payment_identifier = Column(String, nullable=True)

    user = relationship("User", back_populates="recurring_services")
    invoices = relationship(
        "Invoice", back_populates="service", cascade="all, delete-orphan"
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("recurring_services.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(Date, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    is_paid = Column(Boolean, default=False)
    paid_at = Column(DateTime, nullable=True)
    qr_data = Column(Text, nullable=True)

    service = relationship("RecurringService", back_populates="invoices")
