"""Regex extraction (no AI)."""
import re

import numpy as np
import pandas as pd

RE_MID = re.compile(r"\bM\d{4}\b")
RE_PAY = re.compile(r"pay_[A-Za-z0-9]+")
RE_AMT = re.compile(r"Rs\.?\s?([\d,]+)", re.I)
RE_DAYS = re.compile(r"(\d+)\s*(din|days?)\b", re.I)


def extract(ticket: dict) -> dict:
    text = str(ticket.get("merchant_message") or "")
    mid = ticket.get("merchant_id")
    if not mid or (isinstance(mid, float) and np.isnan(mid)):
        m = RE_MID.search(text)
        mid = m.group(0) if m else None
    pay = RE_PAY.search(text)
    amt = RE_AMT.search(text)
    days = RE_DAYS.search(text)
    amount = None
    if amt:
        digits = amt.group(1).replace(",", "")
        amount = int(digits) if digits.isdigit() else None
    return {
        "merchant_id": mid,
        "payment_id": pay.group(0) if pay else None,
        "amount_inr": amount,
        "days_ago": int(days.group(1)) if days else None,
        "created_at": pd.Timestamp(ticket["created_at"]),
    }


def business_days_elapsed(created_at, days_ago):
    """Owner decision J4: weekends excluded, no bank holidays (not in data)."""
    if days_ago is None:
        return None
    end = pd.Timestamp(created_at).date()
    start = end - pd.Timedelta(days=int(days_ago))
    return int(np.busday_count(start, end))
