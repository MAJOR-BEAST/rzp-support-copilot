"""Guardrails: promise firewall (deterministic), specificity test, LLM critic, send mode."""
import re

from .llm import MODEL_FAST, call_json

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
RE_DATE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})[a-z]*\.?,?(?:\s+(\d{{4}}))?\b", re.I)
RE_DATE_MF = re.compile(rf"\b({MONTHS})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?(?:\s+(\d{{4}}))?\b", re.I)
RE_DATE_NUM = re.compile(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{2,4}\b")
RE_IDS = re.compile(r"\bM\d{4}\b|pay_[A-Za-z0-9]+|@\S+")
RE_NUM = re.compile(r"(?:₹|Rs\.?\s?|INR\s?)?\d[\d,]*(?:\.\d+)?", re.I)
RE_DURATION = re.compile(r"\b\d+(?:\s*[-–]\s*\d+)?\s*(?:business\s+|working\s+|calendar\s+)?"
                         r"(?:days?|din|hours?|hrs?|ghante|minutes?|weeks?|months?)\b", re.I)

# (pattern, allowance key or None = always blocked unless no key)
COMMITMENTS = [
    (r"\bwill\s+(?:be\s+)?released\b", "release"), (r"\brelease\s+ho\s+jaye?g[ai]\b", "release"),
    (r"\bwill\s+(?:be\s+)?refunded\b", "refund"), (r"\brefund\s+ho\s+jaye?g[ai]\b", "refund"),
    (r"\bwill\s+(?:be\s+)?credited\b", "credit"), (r"\bcredit\s+ho\s+jaye?g[ai]\b", "credit"),
    (r"\bwill\s+(?:be\s+)?waived\b", None), (r"\bguarantee", None), (r"\bby\s+tomorrow\b", None),
    (r"\bkal\s+tak\b", None), (r"\btoday\s+itself\b", None), (r"\baaj\s+hi\b", None),
    (r"\bwithin\s+(\d+)\s+hours\b", "24h"), (r"waive", None), (r"\bapproved\b", None),
    (r"refund\s+the\s+difference", None), (r"\bwe\s+will\s+release\b", None), (r"\b72\s*hours\b", None),
]
RULE_ALLOW = {"S3": {"release"}, "S4": {"24h"}, "R2": {"credit"}, "S1": {"credit"}}
RISK_REASON = re.compile(r"risk\s+review|chargeback\s+reserve|fraud|suspicious|flagged", re.I)


def _norm_date(d, mon, y):
    return f"{int(d):02d} {mon[:3].title()}" + (f" {y}" if y else "")


def _dates(text):
    out = []
    for m in RE_DATE.finditer(text):
        out.append((m.group(0), _norm_date(m.group(1), m.group(2), m.group(3))))
    for m in RE_DATE_MF.finditer(text):
        out.append((m.group(0), _norm_date(m.group(2), m.group(1), m.group(3))))
    for m in RE_DATE_NUM.finditer(text):
        out.append((m.group(0), m.group(0)))
    return out


def _norm_num(tok):
    n = re.sub(r"(?i)₹|rs\.?|inr|,|\s", "", tok)
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n.lstrip("0") or "0"


def allowed_sets(allowed_facts: dict, kb_texts: list):
    src = " ".join([str(v) for v in allowed_facts.values() if v is not None] + list(kb_texts))
    src = RE_IDS.sub(" ", src)
    dates = {nd for _, nd in _dates(src)}
    dates |= {" ".join(d.split()[:2]) for d in dates}  # "02 Oct 2026" also allows "02 Oct"
    for raw, _ in _dates(src):
        src = src.replace(raw, " ")
    nums = {_norm_num(t) for t in RE_NUM.findall(src)}
    return dates, nums


def firewall(reply: str, card, kb_texts: list):
    """Return (status 'PASS'|'BLOCKED', [offending tokens])."""
    issues = []
    if "{{" in reply or "}}" in reply:
        issues.append("unfilled placeholder: " + ", ".join(re.findall(r"\{\{[^}]*\}\}", reply)))
    text = RE_IDS.sub(" ", reply)
    text = re.sub(r"(?m)^\s*\d+[.)]\s", " ", text)  # list markers "1." are not facts
    ok_dates, ok_nums = allowed_sets(card.allowed_facts, kb_texts)
    for raw, nd in _dates(text):
        if nd not in ok_dates:
            issues.append(f"date not in facts: '{raw.strip()}'")
        text = text.replace(raw, " ")
    for tok in RE_NUM.findall(text):
        if _norm_num(tok) not in ok_nums:
            issues.append(f"number not in facts/KB: '{tok.strip()}'")
    allow = RULE_ALLOW.get(card.rule_id, set())
    for pat, key in COMMITMENTS:
        for m in re.finditer(pat, reply, re.I):
            if key == "24h" and "24h" in allow and m.group(1) == "24":
                continue
            if key and key != "24h" and key in allow:
                continue
            issues.append(f"commitment phrase: '{m.group(0)}'")
    if card.action == "Escalate":
        for m in RE_DURATION.finditer(reply):
            issues.append(f"timeline on escalation: '{m.group(0)}'")
    if card.rule_id in ("S5", "C1", "K2") or card.category == "threat":
        for m in RISK_REASON.finditer(reply):
            issues.append(f"internal risk reason: '{m.group(0)}'")
    return ("BLOCKED" if issues else "PASS"), list(dict.fromkeys(issues))


MERCHANT_FACT_KEYS = {"merchant_id", "expected_settlement_date", "last_settlement_date", "last_settlement_amount_inr",
                      "payment_success_rate_7d_pct", "open_chargebacks", "kyc_status", "settlement_status", "payment_id"}


def specificity(reply: str, card, payment_id=None) -> bool:
    if card.rule_id == "T":
        return True
    if card.action == "Ask for info" and "?" in reply:
        return True
    vals = [str(v) for k, v in card.allowed_facts.items() if k in MERCHANT_FACT_KEYS and v not in (None, "")]
    if payment_id:
        vals.append(payment_id)
    return any(v in reply for v in vals)


CRITIC_SYSTEM = """You are a strict QA reviewer for merchant-support replies at a payment gateway.
Check the reply against this checklist and fail it ONLY for a clear violation:
1. On threat tickets: no admission of fault, no argument, no commitment.
2. Does not blame the merchant's customers or the merchant.
3. Does not reveal internal risk reasons (e.g. risk review, fraud suspicion, reserve).
4. Language matches the merchant (Hinglish ticket -> Hinglish/Latin-script reply; English -> English).
5. No promise of a refund, waiver, release, date or timeline beyond what the decision allows.
6. Addresses the merchant's actual question or, for Ask/Escalate decisions, clearly states the next step.
Return JSON {"pass": true|false, "issues": ["short issue", ...]} (issues empty when pass)."""


def critic(ticket_text: str, card, language: str, reply: str, guidance: str = "", kb_texts=None) -> dict:
    facts = {k: v for k, v in card.allowed_facts.items() if v is not None}
    for k, v in facts.items():
        guidance = guidance.replace("{{" + k + "}}", str(v))
    prompt = (f"Ticket ({language}):\n{ticket_text}\n\nDecision: action={card.action}, team={card.team}, "
              f"rule={card.rule_id}. {card.reason_plain}\n"
              f"VERIFIED SYSTEM FACTS (correct; the reply may state them): {facts}\n"
              f"POLICY-APPROVED CONTENT (stating these policy facts/timelines is ALLOWED, not a promise): {guidance}\n"
              f"CITED KB (any content from here is allowed): {' | '.join(kb_texts or [])}\n"
              f"Note: business days exclude weekends, so a merchant's calendar-day count can exceed business days "
              f"elapsed; that is not a discrepancy. Polite offers to help further are not commitments.\n\n"
              f"Reply:\n{reply}")
    out = call_json(MODEL_FAST, CRITIC_SYSTEM, prompt, max_tokens=600)
    if out.get("_parse_error"):
        return {"pass": False, "issues": ["critic output unparseable -> human review"]}
    return {"pass": bool(out.get("pass")), "issues": [str(i) for i in (out.get("issues") or [])]}


CATEGORY_AUTO_SEND = {c: True for c in ["settlement", "payment_failure", "refund", "chargeback", "kyc", "fees_pricing",
                                        "api_integration", "account_change", "threat", "unclear"]}


def send_mode(card, confidence, sentiment, repeat, fw_status, spec_pass, critic_pass, toggles=None):
    toggles = toggles or CATEGORY_AUTO_SEND
    if fw_status != "PASS":
        return "DO_NOT_SEND"
    if not spec_pass:
        return "HUMAN_WRITE"
    if (card.action == "Auto-resolve" and confidence >= 0.8 and sentiment != "angry" and not repeat
            and not card.mismatch and not card.block_auto and critic_pass and toggles.get(card.category, True)
            and card.category != "threat"):
        return "AUTO_SEND"
    return "HUMAN_REVIEW"
