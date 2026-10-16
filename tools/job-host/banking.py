"""Fictional EUR statement arithmetic. Integer cents; no money-moving operation."""
import hashlib
import json
import uuid

def request_fields(data):
    if not isinstance(data, dict) or set(data) != {'period', 'idempotency_key'}:
        raise ValueError('Only period and idempotency_key are accepted')
    if data['period'] != '2026-09' or not isinstance(data['idempotency_key'], str):
        raise ValueError('September 2026 and a UUID idempotency key required')
    return data['period'], str(uuid.UUID(data['idempotency_key']))

def statement(account, opening, rows):
    if type(opening) is not int or any(type(r[3]) is not int for r in rows):
        raise ValueError('Ledger amounts must be integer cents')
    return {'schema':'statement-v1','account_id':account,'period':'2026-09','currency':'EUR',
            'opening_balance_cents':opening,'credits_cents':sum(max(0,r[3]) for r in rows),
            'debits_cents':-sum(min(0,r[3]) for r in rows),
            'closing_balance_cents':opening+sum(r[3] for r in rows),
            'transactions':[{'id':r[0],'date':str(r[1]),'description':r[2],'amount_cents':r[3]} for r in rows]}

def digest(document):
    return hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
