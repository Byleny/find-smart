from collections import defaultdict
from datetime import date, timedelta
from typing import List

import numpy as np

from schemas import PatternResult, TrendResult


def detect_patterns(transactions) -> List[PatternResult]:
    """
    Detects recurring expense patterns by grouping on exact description (case-insensitive)
    and measuring temporal regularity with the coefficient-of-variation confidence metric.
    Confidence = max(0, 1 - std/mean) of inter-occurrence intervals in days.
    """
    expenses = [t for t in transactions if t.type == "gasto"]
    if len(expenses) < 2:
        return []

    # Group by exact description (normalized to lowercase)
    groups: dict[str, list] = defaultdict(list)
    for t in expenses:
        groups[t.description.lower().strip()].append(t.date)

    results = []
    for desc, dates in groups.items():
        cluster_dates = sorted(dates)

        if len(cluster_dates) < 3:
            continue

        intervals = np.array(
            [(cluster_dates[k] - cluster_dates[k - 1]).days for k in range(1, len(cluster_dates))],
            dtype=float,
        )
        mean_iv = float(np.mean(intervals))
        std_iv = float(np.std(intervals)) if len(intervals) > 1 else 0.0

        # Skip very short intervals (< 7 days) — not meaningful recurring expenses
        if mean_iv < 7:
            continue

        confidence = max(0.0, 1.0 - (std_iv / mean_iv)) if mean_iv > 0 else 0.0

        results.append(
            PatternResult(
                service_id=None,
                service_name=desc,
                detected_day=int(round(mean_iv)),
                confidence=round(confidence, 3),
                next_predicted_date=max(cluster_dates) + timedelta(days=int(round(mean_iv))),
                occurrences=len(cluster_dates),
                first_seen=min(cluster_dates),
                last_seen=max(cluster_dates),
            )
        )

    return sorted(results, key=lambda r: r.confidence, reverse=True)


def analyze_trends(transactions) -> List[TrendResult]:
    """
    Compares the last COMPLETE month vs the average of the 3 months before that.
    Uses complete months so the comparison is always meaningful regardless of
    where we are in the current month.
    avg_last_3m  = last complete month total
    avg_prev_3m  = (month-2 + month-3 + month-4) / 3
    Returns % change and trend direction (sube / baja / estable ±5 %).
    """
    expenses = [t for t in transactions if t.type == "gasto"]
    if not expenses:
        return []

    today = date.today()

    def months_ago(n: int) -> date:
        m, y = today.month - n, today.year
        while m <= 0:
            m += 12
            y -= 1
        return date(y, m, 1)

    start_current = date(today.year, today.month, 1)   # 1st of current month
    start_last    = months_ago(1)                       # 1st of last complete month
    start_prev4   = months_ago(4)                       # 1st of 4 months ago

    last_m  = [t for t in expenses if start_last <= t.date < start_current]
    prev_3m = [t for t in expenses if start_prev4 <= t.date < start_last]

    categories = {t.category for t in last_m} | {t.category for t in prev_3m}

    results = []
    for cat in categories:
        last_total = sum(t.amount for t in last_m  if t.category == cat)
        avg_prev   = sum(t.amount for t in prev_3m if t.category == cat) / 3

        if avg_prev > 0:
            pct = ((last_total - avg_prev) / avg_prev) * 100
        elif last_total > 0:
            pct = 100.0
        else:
            continue

        results.append(
            TrendResult(
                category=cat,
                avg_last_3m=round(last_total, 2),  # gasto del mes pasado
                avg_prev_3m=round(avg_prev, 2),     # promedio 3 meses anteriores
                pct_change=round(pct, 1),
                trend="sube" if pct > 5 else "baja" if pct < -5 else "estable",
            )
        )

    return sorted(results, key=lambda r: abs(r.pct_change), reverse=True)


def predict_next_payment(service, invoices: list) -> dict:
    today = date.today()
    billing_day = service.billing_day

    if invoices:
        invoice_dates = sorted(inv.due_date for inv in invoices)
        last_due = invoice_dates[-1]
        if len(invoice_dates) >= 2:
            intervals = [(invoice_dates[i] - invoice_dates[i - 1]).days for i in range(1, len(invoice_dates))]
            next_date = last_due + timedelta(days=int(round(np.mean(intervals))))
        else:
            m = last_due.month % 12 + 1
            y = last_due.year + (1 if last_due.month == 12 else 0)
            try:
                next_date = date(y, m, billing_day)
            except ValueError:
                next_date = date(y, m + 1, 1) - timedelta(days=1)
    else:
        try:
            candidate = date(today.year, today.month, billing_day)
        except ValueError:
            candidate = date(today.year, today.month + 1, 1) - timedelta(days=1)
        if candidate >= today:
            next_date = candidate
        else:
            m = today.month % 12 + 1
            y = today.year + (1 if today.month == 12 else 0)
            try:
                next_date = date(y, m, billing_day)
            except ValueError:
                next_date = date(y, m + 1, 1) - timedelta(days=1)

    return {
        "service_id": service.id,
        "service_name": service.name,
        "next_predicted_date": str(next_date),
        "days_until": (next_date - today).days,
        "billing_day": billing_day,
        "estimated_amount": service.last_fetched_amount or service.estimated_amount,
    }
