"""
Utilities for currency conversion.
"""
import time
from decimal import Decimal
from typing import Optional

import requests

_FX_CACHE = {"ts": 0.0, "per_inr": {}}  # maps CURRENCY -> amount of that currency per 1 INR
_FX_TTL_SECONDS = 3600

_CURRENCY_MAP = {
    '₹': 'INR', 'RS': 'INR', 'RS.': 'INR', 'INR': 'INR',
    '$': 'USD', 'US$': 'USD', 'USD': 'USD',
    '€': 'EUR', 'EUR': 'EUR',
    '£': 'GBP', 'GBP': 'GBP',
    '¥': 'JPY', 'JPY': 'JPY',
    'C$': 'CAD', 'CAD': 'CAD',
    'A$': 'AUD', 'AUD': 'AUD',
    'SG$': 'SGD', 'SGD': 'SGD',
    'RM': 'MYR', 'MYR': 'MYR',
    'CNY': 'CNY', 'RMB': 'CNY',
}

def _normalize_currency(cur: Optional[str]) -> str:
    if not cur:
        return 'INR'
    s = str(cur).strip()
    if not s:
        return 'INR'
    up = s.upper()
    if up in _CURRENCY_MAP:
        return _CURRENCY_MAP[up]
    if s in _CURRENCY_MAP:
        return _CURRENCY_MAP[s]
    if up.startswith('US$'):
        return 'USD'
    if up.startswith('RS'):
        return 'INR'
    return up

def _get_per_inr_rates() -> dict:
    now = time.time()
    if now - _FX_CACHE["ts"] > _FX_TTL_SECONDS or not _FX_CACHE["per_inr"]:
        try:
            resp = requests.get('https://api.exchangerate.host/latest?base=INR', timeout=8)
            resp.raise_for_status()
            data = resp.json() or {}
            rates = data.get('rates') or {}
            per_inr = {}
            for code, val in rates.items():
                try:
                    per_inr[code.upper()] = Decimal(str(val))
                except Exception:
                    continue
            if per_inr:
                _FX_CACHE["per_inr"] = per_inr
                _FX_CACHE["ts"] = now
        except Exception:
            pass
    return _FX_CACHE["per_inr"]

def convert_to_inr(amount: Decimal, currency: Optional[str]) -> Decimal:
    try:
        amt = Decimal(str(amount))
    except Exception:
        return Decimal('0')
    cur = _normalize_currency(currency)
    if cur == 'INR':
        return amt
    rates = _get_per_inr_rates()
    per_inr = rates.get(cur)
    try:
        if per_inr and per_inr != 0:
            return (amt / per_inr)
    except Exception:
        pass
    INR_PER = {
        'USD': Decimal('84'), 'EUR': Decimal('92'), 'GBP': Decimal('108'),
        'JPY': Decimal('0.55'), 'CAD': Decimal('62'), 'AUD': Decimal('57'),
        'SGD': Decimal('62'), 'MYR': Decimal('18'), 'CNY': Decimal('11'),
    }
    if cur in INR_PER:
        return amt * INR_PER[cur]
    return amt
