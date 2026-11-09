"""Interactive flowchart: parses assets/flowchart/Razorpay.drawio (the design this copilot was built from),
joins it with the 150 triaged tickets, and renders a self-contained SVG + JS explorer (ui/flowchart_template.html)."""
import html as _html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DRAWIO = ROOT / "assets" / "flowchart" / "Razorpay.drawio"
TEMPLATE = Path(__file__).resolve().parent / "flowchart_template.html"

KIND_BY_FILL = {
    "#D5E8D4": "answer", "#E1D5E7": "ask", "#F8CECC": "escalate", "#DAE8FC": "ai", "#ECEFF1": "rule",
    "#FFF2CC": "question", "#1F3A93": "start", "#37474F": "topic", "#FAFAFA": "stage", "#FFFFFF": "note",
    "#FFE0B2": "decisions",
}

# How each box is implemented in this repo (shown in the click-through panel)
INFO = {
    "n3": ("Loads the P1_Tickets tab (150 tickets) from the data pack.", "copilot/data_loader.py"),
    "n4": ("Regex only, no AI: merchant ID (M####), payment ID (pay_…), Rs amount, “N din / days”.", "copilot/extract.py"),
    "n5": ("Keyword regex in English + Hinglish (legal notice, RBI, police, data leak, bribe…) OR the classifier labels it a threat.", "copilot/threats.py"),
    "n6": ("Fixed acknowledgement template in English or Hinglish — no AI-written text, never auto-sent.", "copilot/draft.py · rule T"),
    "n7": ("Merchant ID from the ticket column, else an M#### pattern in the text.", "copilot/rules.py · rule Q1"),
    "n8": ("Asks for the merchant ID (and payment ID when it is about a payment or refund).", "copilot/rules.py · rule Q1"),
    "n9": ("Claude Haiku 5.5 returns JSON: 10 categories, 27 sub-intents, confidence, sentiment, language. Every response is cached.", "copilot/classify.py"),
    "n10": ("Owner decision J6: below 80% confidence the copilot asks instead of answering.", "copilot/rules.py · rule Q2"),
    "n11": ("One targeted question that mentions the merchant's current account status.", "copilot/rules.py · rule Q2"),
    "n12": ("Merchant row from P1_Merchants. Repeat contact = this is their 4th+ ticket, counting only earlier tickets.", "run_pipeline.py · repeat_contact_flags()"),
    "n13": ("Deterministic check: claims ‘not received’ but status Settled, or dispute debit with 0 open chargebacks.", "copilot/rules.py · mismatch"),
    "n14": ("Owner decision J9: threat > closure > settlement hold > refund ≥ ₹1L > payment failure > others.", "copilot/rules.py · _rank()"),
    "n15": ("The policy engine picks the topic branch and returns a DecisionCard.", "copilot/rules.py · decide()"),
    "n123": ("DecisionCard: category, action, team, risk, rule id, KB ids, allowed facts, flags.", "copilot/rules.py · DecisionCard"),
    "n122": ("Applied after the rule: angry +1 risk, repeat +1 risk, mismatch blocks auto-send, urgency never adds dates.", "copilot/rules.py · _modifiers()"),
    "n125": ("Pinecone index rzp-kb with multilingual-e5-large (top-3), always unioned with the rule's own KB articles. TF-IDF fallback.", "copilot/vectorstore.py"),
    "n126": ("Claude Sonnet 5.5 writes {{placeholders}}; Python fills them with the real system values.", "copilot/draft.py"),
    "n127": ("Promise firewall: every date, amount and duration must exist in the allowed facts or cited KB; blocks “72 hours”, “approved”, “waive”…", "copilot/guardrails.py · firewall()"),
    "n128": ("Blocked drafts are written to outputs/would_not_send.csv with the exact offending phrase.", "copilot/batch.py"),
    "n129": ("Reply must use a merchant-specific value (or ask a direct question). One rewrite, then HUMAN_WRITE.", "copilot/guardrails.py · specificity()"),
    "n130": ("Send mode HUMAN_WRITE.", "copilot/draft.py"),
    "n131": ("Claude Haiku 5.5 reviews tone, blame, leaked risk reasons, language and promises.", "copilot/guardrails.py · critic()"),
    "n132": ("Auto-send only if Auto-resolve, ≥80% confident, calm, not repeat, records match, firewall + specificity + critic pass.", "copilot/guardrails.py · send_mode()"),
    "n133": ("Send mode AUTO_SEND.", "copilot/guardrails.py"),
    "n134": ("This console: Copilot View with summary, reasoning, draft, KB chips and Approve / Edit / Escalate.", "app.py · Copilot View"),
    "n144": ("The per-category auto-send toggles in the sidebar of this console.", "app.py · sidebar"),
    "n146": ("Sliding 24h window over payment-failure tickets; ≥3 distinct merchants → incident (flag only).", "copilot/batch.py · find_incidents()"),
    "n147": ("Tickets flagged kb_gap (or weak retrieval) grouped by sub-intent → suggested article.", "copilot/batch.py · find_kb_gaps()"),
    "n148": ("outputs/triage_results.xlsx — all 150 rows, 26 columns + summary sheet.", "run_pipeline.py"),
    "n149": ("Built version scores all 150 tickets against data/answer_key.csv → outputs/metrics.md.", "copilot/evaluate.py"),
}
RULE_NODE = {"T": "n6", "Q1": "n8", "Q2": "n11", "S2": "n32", "S1": "n36", "S3": "n40", "S4": "n44", "S5": "n47",
             "P1": "n51", "P2": "n55", "P3": "n58", "R0": "n62", "R1": "n66", "R3": "n70", "R2": "n73", "C1": "n77",
             "C2": "n81", "C3": "n84", "K3": "n88", "K1": "n92", "K2": "n95", "F1": "n99", "F2": "n102", "A1": "n106",
             "A2": "n109", "AC1": "n113", "AC2": "n117", "AC3": "n120"}
RULE_KB = {"S1": "KB-01, KB-02", "S2": "KB-01", "S3": "KB-04", "S4": "KB-05", "S5": "KB-03", "P2": "KB-06", "P3": "KB-06",
           "R0": "KB-16", "R1": "KB-07", "R2": "KB-07", "R3": "KB-07", "C1": "KB-08", "C2": "KB-08", "C3": "KB-08",
           "K1": "KB-10", "K2": "KB-10", "K3": "KB-10", "F1": "KB-09", "F2": "KB-09", "A1": "KB-12 / 13 / 14",
           "AC1": "KB-11", "AC2": "KB-11", "AC3": "KB-17", "T": "KB-15", "Q1": "KB-16", "Q2": "KB-16"}


def _text(v):
    v = re.sub(r"<br\s*/?>", "\n", v or "")
    v = re.sub(r"<[^>]+>", "", v)
    return _html.unescape(v).strip()


def load_graph():
    root = ET.parse(DRAWIO).getroot()
    nodes, edges = [], []
    for c in root.iter("mxCell"):
        st = c.get("style") or ""
        if c.get("edge") == "1":
            edges.append({"id": c.get("id"), "s": c.get("source"), "t": c.get("target"), "label": _text(c.get("value"))})
            continue
        if c.get("vertex") != "1":
            continue
        g = c.find("mxGeometry")
        x, y, w, h = (float(g.get(k, 0)) for k in ("x", "y", "width", "height"))
        fill = (re.search(r"fillColor=(#[0-9A-Fa-f]{6})", st) or [None, ""])[1].upper()
        shape = "rhombus" if "rhombus" in st else "text" if st.startswith("text") else "box"
        kind = "title" if shape == "text" else KIND_BY_FILL.get(fill, "note")
        lines = [ln.strip() for ln in _text(c.get("value")).split("\n")]
        nodes.append({"id": c.get("id"), "x": x, "y": y, "w": w, "h": h, "shape": shape, "kind": kind,
                      "title": lines[0] if lines else "", "lines": lines[1:]})
    stages = [n for n in nodes if n["kind"] == "stage"]
    for n in nodes:
        n["stage"] = next((s["title"].split("·")[0].strip().title() for s in stages if n is not s
                           and s["x"] <= n["x"] and n["x"] + n["w"] <= s["x"] + s["w"] + 1
                           and s["y"] <= n["y"] and n["y"] + n["h"] <= s["y"] + s["h"] + 1), "Reference")
        if n["id"] in INFO:
            n["impl"], n["file"] = INFO[n["id"]]
        rules = [r for r, nid in RULE_NODE.items() if nid == n["id"]]
        if rules:
            n["rule"] = rules[0]
            n["kb"] = RULE_KB.get(rules[0], "")
            n.setdefault("impl", "Outcome of the deterministic policy engine for this branch.")
            n.setdefault("file", f"copilot/rules.py · rule {rules[0]}")
    return nodes, edges


def _short(s, n=170):
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1] + "…"


def build_html(res: pd.DataFrame, flowchart_url: str = "") -> str:
    nodes, edges = load_graph()
    tickets = []
    for r in res.to_dict("records"):
        tickets.append({
            "id": r["ticket_id"], "at": pd.Timestamp(r["created_at"]).strftime("%d %b %H:%M"), "ch": r["channel"],
            "m": r["merchant_id"] or "", "msg": r["merchant_message"], "lang": r["language"], "sent": r["sentiment"],
            "cat": r["category"], "sub": r["sub_intent"], "conf": float(r["confidence"] or 0), "act": r["action"],
            "team": r["escalation_team"], "risk": r["risk"], "rule": r["rule_id"], "why": r["reason_plain"],
            "kb": r["kb_cited"], "reply": r["drafted_reply"], "send": r["send_mode"], "fw": r["firewall_status"],
            "fwi": r["firewall_issue"], "spec": str(r["specificity_pass"]).lower() in ("true", "1"),
            "crit": _short(r["critic_issues"]), "rep": str(r["repeat_contact"]).lower() in ("true", "1"),
            "mis": r["mismatch"], "inc": r["incident_id"], "flags": r["flags"], "sum": r["summary_one_line"],
        })
    data = {"nodes": nodes, "edges": edges, "tickets": tickets, "ruleNode": RULE_NODE, "drawioUrl": flowchart_url}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
