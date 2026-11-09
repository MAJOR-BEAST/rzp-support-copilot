"""LLM intent classifier (MODEL_FAST, JSON only, cached)."""
from .llm import MODEL_FAST, call_json

SUB_INTENTS = {
    "settlement": ["settlement_status"],
    "payment_failure": ["payment_failure_general", "tech_error_unknown"],
    "refund": ["refund_status"],
    "chargeback": ["chargeback_what_to_do", "chargeback_block_request", "chargeback_debit_no_notice"],
    "kyc": ["kyc_documents", "kyc_reverify_genuine"],
    "fees_pricing": ["fees_invoice", "fees_negotiation"],
    "api_integration": ["api_signature", "api_amount_mismatch", "api_auth_failed", "api_webhook", "api_unknown"],
    "account_change": ["account_contact_change", "account_entity_change", "account_closure"],
    "threat": ["threat_legal", "threat_regulator", "threat_security", "threat_media", "threat_bribery"],
    "unclear": ["unclear"],
}
SUB_TO_CAT = {s: c for c, subs in SUB_INTENTS.items() for s in subs}

SYSTEM = """You classify merchant support tickets for an Indian payment gateway (Razorpay-like).
Messages are in English or Hinglish (Hindi written in Latin script, e.g. "paisa kab milega").

CATEGORIES and SUB-INTENTS (pick exactly one sub_intent from the chosen category):
settlement
  - settlement_status: merchant asks where their payout/settlement is, why it is late, or why payouts are on hold / asks to release a hold.
payment_failure
  - payment_failure_general: their customers' payments are failing / declining / money deducted but order failed / success rate dropped.
  - tech_error_unknown: a payment failure described only as an unexplained technical error with no known fix.
refund
  - refund_status: merchant asks about the status of a refund to their customer.
chargeback
  - chargeback_what_to_do: merchant received a chargeback/dispute and asks what to do, by when, or how to fight it.
  - chargeback_block_request: merchant wants a likely future dispute stopped/blocked in advance.
  - chargeback_debit_no_notice: money was debited for a dispute but merchant says they never saw any notice.
kyc
  - kyc_documents: which documents are needed for KYC.
  - kyc_reverify_genuine: merchant got a KYC re-verification message and asks if it is genuine.
fees_pricing
  - fees_invoice: merchant wants their GST/fee invoice or where to download it.
  - fees_negotiation: fee waiver request, MDR/rate dispute, asks for lower rate, competitor threat, refund of fee difference.
api_integration
  - api_signature: SIGNATURE_MISMATCH / signature verification failing.
  - api_amount_mismatch: BAD_REQUEST_ERROR order amount mismatch.
  - api_auth_failed: "Authentication failed" on live site (test vs live keys).
  - api_webhook: webhooks not received.
  - api_unknown: any other API/technical error with no known fix: 502s, timeouts, rate-limiting, blank checkout popup, intermittent errors.
account_change
  - account_contact_change: change registered email / mobile.
  - account_entity_change: change company/legal name or business type.
  - account_closure: wants to close the account.
threat
  - threat_legal: legal notice, lawyer, court, consumer forum, police, accusing company of fraud.
  - threat_regulator: complaint to RBI / regulator / ombudsman.
  - threat_security: data leak, account takeover, unauthorised dashboard/bank changes.
  - threat_media: threatens to post on Twitter/LinkedIn/press/media.
  - threat_bribery: staff asked for commission/bribe.
unclear
  - unclear: too vague to tell what the problem is (e.g. "help", "not working", "check my case", "payment problem", "money not received" with no detail).

Rules:
- "category" must be one of the 10 category names above (never a sub-intent name).
- Customers' payments failing / declining at checkout (UPI, cards), even phrased as a question "is there an issue at your end?", is payment_failure / payment_failure_general with high confidence.
- A technical symptom (timeouts, 5xx errors, rate-limiting, blank popup, page not loading) is api_integration / api_unknown, not payment_failure_general.
- confidence (0-1): how sure you are of category AND sub_intent. Use < 0.8 when the message is vague or could fit several sub-intents. A very short message like "Payment failed." with no detail is ambiguous (single payment vs. widespread) -> confidence 0.6.
- secondary_category: another category also clearly raised in the message, else null. secondary_sub_intent likewise.
- sentiment: calm (neutral question) | frustrated (complaint, urgency, repeated problem, "please release", "!!") | angry (threats, insults, ultimatums, accusing of fraud, legal/media/regulator threats, "close my account and send all money now", demands with "immediately or I will move").
- language: Hinglish if the message contains Hindi words in Latin script (kyun, kab, mera, nahi, hai, karo, bhai, din...), else English.
- summary_one_line: <= 15 words, plain English.

Return JSON: {"category":..., "sub_intent":..., "secondary_category":null, "secondary_sub_intent":null, "confidence":0.0, "sentiment":..., "language":..., "summary_one_line":..., "reasoning_short":...}

EXAMPLES
1. "Bhai mera payout teen din se nahi aaya, kab aayega?" ->
{"category":"settlement","sub_intent":"settlement_status","secondary_category":null,"secondary_sub_intent":null,"confidence":0.95,"sentiment":"frustrated","language":"Hinglish","summary_one_line":"Merchant asks when delayed payout will arrive.","reasoning_short":"Asks about payout timing."}
2. "If my money is not released by tonight I am filing a case in consumer court and calling my lawyer." ->
{"category":"threat","sub_intent":"threat_legal","secondary_category":"settlement","secondary_sub_intent":"settlement_status","confidence":0.97,"sentiment":"angry","language":"English","summary_one_line":"Merchant threatens legal action over withheld funds.","reasoning_short":"Mentions consumer court and lawyer."}
3. "Refund ka status batao, pay_ABC123XYZ, Rs 5,000, 4 din ho gaye." ->
{"category":"refund","sub_intent":"refund_status","secondary_category":null,"secondary_sub_intent":null,"confidence":0.95,"sentiment":"frustrated","language":"Hinglish","summary_one_line":"Merchant asks refund status for a payment after 4 days.","reasoning_short":"Refund status with payment ID."}
4. "Our checkout API returns 504 gateway timeout randomly, no error code in logs." ->
{"category":"api_integration","sub_intent":"api_unknown","secondary_category":null,"secondary_sub_intent":null,"confidence":0.9,"sentiment":"calm","language":"English","summary_one_line":"Random 504 timeouts from API with no error code.","reasoning_short":"Unknown technical error, no KB fix."}
5. "Tumhare ek banda ne settlement jaldi karne ke liye paise maange. Ye kya hai?" ->
{"category":"threat","sub_intent":"threat_bribery","secondary_category":"settlement","secondary_sub_intent":"settlement_status","confidence":0.95,"sentiment":"angry","language":"Hinglish","summary_one_line":"Merchant alleges staff asked for money to speed settlement.","reasoning_short":"Bribery allegation against staff."}
6. "Something is wrong, please call me." ->
{"category":"unclear","sub_intent":"unclear","secondary_category":null,"secondary_sub_intent":null,"confidence":0.4,"sentiment":"calm","language":"English","summary_one_line":"Vague request for a call; problem not stated.","reasoning_short":"No issue described."}
"""


def classify(message: str) -> dict:
    out = call_json(MODEL_FAST, SYSTEM, f"Ticket message:\n{message}")
    cat = out.get("category")
    sub = out.get("sub_intent")
    if cat not in SUB_INTENTS:  # model sometimes returns the sub-intent as the category
        cat = SUB_TO_CAT.get(cat) or SUB_TO_CAT.get(sub) or "unclear"
    if sub not in SUB_INTENTS[cat]:
        sub = SUB_INTENTS[cat][0] if cat != "unclear" else "unclear"
    sec = out.get("secondary_category")
    if sec not in SUB_INTENTS:
        sec = SUB_TO_CAT.get(sec)
    # threats come only from keywords or a PRIMARY threat classification (§3.3)
    sec = sec if sec and sec != cat and sec not in ("threat", "unclear") else None
    sec_sub = out.get("secondary_sub_intent")
    if sec and sec_sub not in SUB_INTENTS[sec]:
        sec_sub = SUB_INTENTS[sec][0]
    try:
        conf = float(out.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    sent = out.get("sentiment") if out.get("sentiment") in ("calm", "frustrated", "angry") else "calm"
    lang = out.get("language") if out.get("language") in ("English", "Hinglish") else "English"
    return {
        "category": cat, "sub_intent": sub, "secondary_category": sec,
        "secondary_sub_intent": sec_sub if sec else None, "confidence": round(conf, 2),
        "sentiment": sent, "language": lang,
        "summary_one_line": out.get("summary_one_line", ""), "reasoning_short": out.get("reasoning_short", ""),
    }
