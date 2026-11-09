"""Deterministic policy engine (CLAUDE.md §5) -> DecisionCard."""
from dataclasses import asdict, dataclass, field

from .extract import business_days_elapsed
from .threats import SUBINTENT_TEAM

AUTO, ASK, ESC = "Auto-resolve", "Ask for info", "Escalate"
RISKS = ["Low", "Medium", "High", "Critical"]
URGENCY = ("today", "urgent", "abhi", "immediately", "asap", "tonight")


@dataclass
class DecisionCard:
    category: str
    sub_intent: str
    action: str
    team: str
    risk: str
    rule_id: str
    kb_ids: list
    allowed_facts: dict
    flags: list = field(default_factory=list)
    reason_plain: str = ""
    base_risk: str = ""
    mismatch: str = ""
    block_auto: bool = False

    def to_dict(self):
        return asdict(self)


def fmt_inr(v):
    return f"Rs {int(v):,}" if v is not None else None


def _risk_up(r):
    return RISKS[min(RISKS.index(r) + 1, 3)]


def _rank(cat, sub, merchant, ext):
    if cat == "threat":
        return 6
    if cat == "account_change" and sub == "account_closure":
        return 5
    if cat == "settlement" and merchant and merchant.get("settlement_status") == "On hold":
        return 4
    if cat == "refund" and (ext.get("amount_inr") or 0) >= 100000:
        return 3
    if cat == "payment_failure":
        return 2
    return 1


def _card(cat, sub, action, team, risk, rule, kbs, facts, reason, flags=None):
    return DecisionCard(cat, sub, action, team, risk, rule, kbs, facts, flags or [], reason, base_risk=risk)


def decide(ticket: dict, ext: dict, cls: dict, merchant: dict | None, repeat_contact: bool, threat) -> DecisionCard:
    text = str(ticket.get("merchant_message") or "")
    mid = ext.get("merchant_id")
    pay = ext.get("payment_id")

    # ---- Stage 1 gate: threat (keyword OR classifier) ----
    if threat or cls["category"] == "threat":
        if threat:
            sub, team, kw = threat
        else:
            sub = cls["sub_intent"]
            team, kw = SUBINTENT_TEAM.get(sub, "Legal"), "classifier"
        card = _card("threat", sub, ESC, team, "Critical", "T", ["KB-15"],
                     {"team": team, **({"merchant_id": mid} if mid else {})},
                     f"Threat detected ({kw}); acknowledge only and escalate to {team}.", ["threat"])
        return _modifiers(card, cls, repeat_contact, text)

    # ---- no merchant ID -> Q1 ----
    if not mid or merchant is None:
        facts = {"payment_id": pay} if pay else {}
        cat = cls["category"] if cls["confidence"] >= 0.8 else "unclear"
        card = _card(cat, cls["sub_intent"] if cat != "unclear" else "unclear", ASK, "None", "Low", "Q1", ["KB-16"],
                     facts, "No merchant ID on ticket; ask for it (and payment ID if about a payment/refund).")
        return _modifiers(card, cls, repeat_contact, text)

    base = {"merchant_id": mid}

    # ---- low confidence / unclear -> Q2 ----
    if cls["confidence"] < 0.8 or cls["category"] == "unclear":
        facts = {**base, "settlement_status": merchant.get("settlement_status"), "kyc_status": merchant.get("kyc_status")}
        card = _card(cls["category"] if cls["category"] != "unclear" else "unclear",
                     cls["sub_intent"], ASK, "None", "Medium", "Q2", ["KB-16"], facts,
                     f"Intent unclear (confidence {cls['confidence']:.2f}); ask one targeted question.")
        return _modifiers(card, cls, repeat_contact, text)

    # ---- multi-intent: higher-risk category decides ----
    cat, sub = cls["category"], cls["sub_intent"]
    if cls.get("secondary_category") and cls["secondary_category"] != "unclear":
        s_cat, s_sub = cls["secondary_category"], cls["secondary_sub_intent"]
        if s_cat != "threat" and _rank(s_cat, s_sub, merchant, ext) > _rank(cat, sub, merchant, ext):
            cat, sub = s_cat, s_sub

    m = merchant
    card = None
    if cat == "settlement":
        st = m.get("settlement_status")
        if st == "Delayed":
            card = _card(cat, sub, AUTO, "None", "Low", "S1", ["KB-01", "KB-02"],
                         {**base, "expected_settlement_date": m.get("expected_settlement_date")},
                         "Settlement delayed bank-side; share system expected date.")
        elif st == "Settled":
            card = _card(cat, sub, AUTO, "None", "Low", "S2", ["KB-01"],
                         {**base, "last_settlement_date": m.get("last_settlement_date"),
                          "last_settlement_amount_inr": fmt_inr(m.get("last_settlement_amount_inr"))},
                         "System shows last settlement completed; share date/amount, ask UTR if not visible.")
            card.mismatch = "claims not received; system shows Settled"
        else:
            hr = m.get("hold_reason")
            if hr == "KYC pending":
                card = _card(cat, sub, AUTO, "None", "Medium", "S3", ["KB-04"], {**base},
                             "Payout on hold for pending KYC; guide to Dashboard > Account > KYC.")
            elif hr == "Bank account mismatch":
                card = _card(cat, sub, AUTO, "None", "Medium", "S4", ["KB-05"], {**base},
                             "Payout on hold for bank account name mismatch; re-add account.")
            else:
                card = _card(cat, sub, ESC, "Risk Ops", "High", "S5", ["KB-03"], {**base},
                             "Payout hold needs Risk Ops review; no reason or timeline to merchant.")
    elif cat == "payment_failure":
        sr = m.get("payment_success_rate_7d_pct")
        if sub == "tech_error_unknown":
            card = _card(cat, sub, ESC, "Tech Support", "High", "P1", [], {**base},
                         "Unknown technical error with no KB article.", ["kb_gap"])
        elif sr is not None and sr < 85:
            card = _card(cat, sub, ESC, "Payments Ops", "High", "P2", ["KB-06"],
                         {**base, "payment_success_rate_7d_pct": f"{sr}%"},
                         f"7-day success rate {sr}% < 85%: possible degradation.")
        else:
            card = _card(cat, sub, AUTO, "None", "Low", "P3", ["KB-06"], {**base},
                         f"Success rate {sr}% healthy; standard retry guidance.")
    elif cat == "refund":
        amt = ext.get("amount_inr")
        if not pay:
            card = _card(cat, sub, ASK, "None", "Low", "R0", ["KB-16"], {**base}, "Refund query without payment ID.")
        elif amt is not None and amt >= 100000:
            card = _card(cat, sub, ESC, "Refund Ops", "High", "R1", ["KB-07"], {**base, "payment_id": pay},
                         f"Refund {fmt_inr(amt)} >= Rs 1,00,000 needs Refund Ops approval; no timeline.")
        else:
            bde = business_days_elapsed(ext["created_at"], ext.get("days_ago"))
            if bde is not None and bde > 7:
                card = _card(cat, sub, ESC, "Refund Ops", "Medium", "R3", ["KB-07"], {**base, "payment_id": pay},
                             f"{bde} business days elapsed (> 7): past SLA, escalate.")
            else:
                card = _card(cat, sub, AUTO, "None", "Low", "R2", ["KB-07"], {**base, "payment_id": pay},
                             f"Within refund SLA ({bde if bde is not None else 'unknown'} business days elapsed).")
    elif cat == "chargeback":
        ocb = m.get("open_chargebacks") or 0
        if sub == "chargeback_debit_no_notice" and ocb == 0:
            card = _card(cat, sub, ESC, "Risk Ops", "High", "C1", ["KB-08"], {**base},
                         "Dispute debit claimed but system shows 0 open chargebacks.", ["mismatch"])
            card.mismatch = "claims dispute debit; system shows 0 open chargebacks"
        elif sub == "chargeback_block_request":
            card = _card(cat, sub, AUTO, "None", "Medium", "C2", ["KB-08"], {**base},
                         "Disputes cannot be blocked in advance.")
        else:
            card = _card(cat, sub, AUTO, "None", "Medium", "C3", ["KB-08"], {**base, "open_chargebacks": ocb},
                         "Standard chargeback guidance: Dashboard > Disputes, evidence within 7 calendar days.")
    elif cat == "kyc":
        ks = m.get("kyc_status")
        if sub == "kyc_reverify_genuine":
            if ks == "Re-verification needed":
                card = _card(cat, sub, AUTO, "None", "Medium", "K1", ["KB-10"], {**base, "kyc_status": ks},
                             "Re-verification genuinely pending; point to Dashboard.")
            else:
                card = _card(cat, sub, ESC, "Security", "High", "K2", ["KB-10"], {**base},
                             f"KYC status is {ks}, so re-verification message is likely phishing.", ["phishing"])
        else:
            card = _card(cat, sub, AUTO, "None", "Low", "K3", ["KB-10"], {**base}, "KYC document list.")
    elif cat == "fees_pricing":
        if sub == "fees_negotiation":
            card = _card(cat, sub, ESC, "Account Manager", "Medium", "F1", ["KB-09"], {**base},
                         "Pricing/waiver request: Account Manager only; no promise.", ["churn_risk"])
        else:
            card = _card(cat, sub, AUTO, "None", "Low", "F2", ["KB-09"], {**base},
                         "Invoices generated by 5th under Dashboard > Reports > Invoices.")
    elif cat == "api_integration":
        if sub == "api_unknown":
            card = _card(cat, sub, ESC, "Tech Support", "High", "A2", [], {**base},
                         "Technical error with no KB article.", ["kb_gap"])
        else:
            kb = {"api_signature": "KB-12", "api_amount_mismatch": "KB-12", "api_auth_failed": "KB-14",
                  "api_webhook": "KB-13"}[sub]
            card = _card(cat, sub, AUTO, "None", "Low", "A1", [kb], {**base}, f"Known API issue; fix steps from {kb}.")
    elif cat == "account_change":
        if sub == "account_closure":
            card = _card(cat, sub, ESC, "Account Manager + Risk Ops", "Medium", "AC3", ["KB-17"], {**base},
                         "Closure only after settlements/refunds/disputes cleared.", ["churn_risk"])
        elif sub == "account_entity_change":
            card = _card(cat, sub, AUTO, "None", "Low", "AC2", ["KB-11"], {**base}, "Entity change needs fresh application.")
        else:
            card = _card(cat, sub, AUTO, "None", "Low", "AC1", ["KB-11"], {**base}, "Email/mobile change via Settings with OTP.")
    if card is None:  # safety net
        card = _card("unclear", "unclear", ASK, "None", "Medium", "Q2", ["KB-16"], {**base}, "No rule matched.")
    return _modifiers(card, cls, repeat_contact, text)


def _modifiers(card: DecisionCard, cls: dict, repeat_contact: bool, text: str) -> DecisionCard:
    if cls.get("sentiment") == "angry":
        card.risk = _risk_up(card.risk)
        card.block_auto = True
        card.flags.append("angry")
    if repeat_contact:
        card.risk = _risk_up(card.risk)
        card.block_auto = True
        card.flags.append("repeat_contact")
    if card.mismatch:
        card.block_auto = True
        if "mismatch" not in card.flags:
            card.flags.append("mismatch")
    if any(w in text.lower() for w in URGENCY):
        card.flags.append("urgency_no_dates")
    return card
