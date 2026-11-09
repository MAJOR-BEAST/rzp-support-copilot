import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from copilot.extract import business_days_elapsed  # noqa: E402
from copilot.guardrails import firewall, send_mode  # noqa: E402
from copilot.rules import DecisionCard, decide  # noqa: E402
from copilot.threats import detect_threat  # noqa: E402
from run_pipeline import repeat_contact_flags  # noqa: E402

KB01 = "Standard settlements are credited T+2 business days after payment capture."
KB02 = "Settlements can be delayed by up to 2 additional business days due to bank-side processing."


def card(rule, action="Auto-resolve", facts=None, category="settlement"):
    return DecisionCard(category, "x", action, "None", "Low", rule, [], facts or {"merchant_id": "M1003"})


def test_blocks_72_hours_release():
    st, issues = firewall("Your payout will be released within 72 hours. — Razorpay Support",
                          card("S5", "Escalate"), [])
    assert st == "BLOCKED"
    assert any("72" in i for i in issues)


def test_blocks_refund_approved():
    st, issues = firewall("Good news, refund of Rs 50,000 approved for M1003.", card("R2"), [])
    assert st == "BLOCKED"
    assert any("approved" in i for i in issues)
    assert any("50,000" in i for i in issues)


def test_blocks_invented_date():
    c = card("S1", facts={"merchant_id": "M1003", "expected_settlement_date": "02 Oct 2026"})
    st, issues = firewall("Your settlement for M1003 is expected on 05 Oct 2026.", c, [KB01, KB02])
    assert st == "BLOCKED"
    assert any("05 Oct 2026" in i for i in issues)


def test_allows_s1_system_date():
    c = card("S1", facts={"merchant_id": "M1003", "expected_settlement_date": "02 Oct 2026"})
    st, issues = firewall("Hi, settlement for M1003 is delayed bank-side by up to 2 business days; the system "
                          "shows the expected date as 02 Oct 2026. — Razorpay Support", c, [KB01, KB02])
    assert st == "PASS", issues


def test_threat_never_auto_send():
    text = "I will send a legal notice and go to consumer court. M1034"
    threat = detect_threat(text)
    cls = {"category": "fees_pricing", "sub_intent": "fees_invoice", "secondary_category": None,
           "secondary_sub_intent": None, "confidence": 0.99, "sentiment": "calm", "language": "English"}
    c = decide({"merchant_message": text}, {"merchant_id": "M1034", "payment_id": None, "amount_inr": None,
                                            "days_ago": None, "created_at": pd.Timestamp("2026-09-05")},
               cls, {"settlement_status": "Settled"}, False, threat)
    assert c.rule_id == "T" and c.action == "Escalate" and c.risk == "Critical" and c.team == "Legal"
    assert send_mode(c, 0.99, "calm", False, "PASS", True, True) != "AUTO_SEND"


def test_business_days():
    # Mon 21 Sep 2026, "7 days" -> start Mon 14 Sep -> 5 business days
    assert pd.Timestamp("2026-09-21").day_name() == "Monday"
    assert business_days_elapsed(pd.Timestamp("2026-09-21 10:00"), 7) == 5


def test_repeat_contact_counts_only_earlier():
    df = pd.DataFrame({
        "ticket_id": ["A", "B", "C", "D", "E"],
        "created_at": pd.to_datetime(["2026-09-05", "2026-09-01", "2026-09-03", "2026-09-04", "2026-09-02"]),
        "merchant_id": ["M1001"] * 5,
        "merchant_message": ["x"] * 5,
    })
    f = repeat_contact_flags(df)
    # order: B(1) E(2) C(3) D(4) A(5)
    assert f["B"] is False and f["E"] is False and f["C"] is False
    assert f["D"] is True and f["A"] is True
