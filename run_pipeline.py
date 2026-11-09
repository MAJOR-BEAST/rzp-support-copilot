"""End-to-end pipeline over the 150 tickets -> outputs/.  NEVER reads data/answer_key.csv.

Usage: python run_pipeline.py [--no-draft] [--workers 8]
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from copilot.classify import classify
from copilot.data_loader import load_kb, load_merchants, load_tickets
from copilot.extract import extract
from copilot.llm import STATS
from copilot.rules import decide
from copilot.threats import detect_threat

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

COLUMNS = ["ticket_id", "created_at", "channel", "merchant_id", "merchant_message", "language", "sentiment",
           "category", "sub_intent", "confidence", "action", "escalation_team", "risk", "rule_id", "reason_plain",
           "kb_cited", "drafted_reply", "send_mode", "firewall_status", "firewall_issue", "specificity_pass",
           "critic_issues", "repeat_contact", "mismatch", "incident_id", "flags"]


def repeat_contact_flags(tickets: pd.DataFrame) -> dict:
    """4th-or-later ticket of a merchant by created_at; counts only earlier + current tickets."""
    out, seen = {}, {}
    for _, r in tickets.sort_values(["created_at", "ticket_id"]).iterrows():
        mid = extract(r.to_dict())["merchant_id"]
        if mid:
            seen[mid] = seen.get(mid, 0) + 1
            out[r["ticket_id"]] = seen[mid] >= 4
        else:
            out[r["ticket_id"]] = False
    return out


def triage(ticket: dict, merchants: dict, repeat: bool, cls: dict | None = None):
    ext = extract(ticket)
    threat = detect_threat(ticket["merchant_message"])
    cls = cls or classify(ticket["merchant_message"])
    merchant = merchants.get(ext["merchant_id"]) if ext["merchant_id"] else None
    card = decide(ticket, ext, cls, merchant, repeat, threat)
    return ext, cls, merchant, card


def base_row(ticket, ext, cls, card, repeat):
    return {
        "ticket_id": ticket["ticket_id"], "created_at": ticket["created_at"], "channel": ticket.get("channel"),
        "merchant_id": ext["merchant_id"], "merchant_message": ticket["merchant_message"],
        "language": cls["language"], "sentiment": cls["sentiment"], "category": card.category,
        "sub_intent": card.sub_intent, "confidence": cls["confidence"], "action": card.action,
        "escalation_team": card.team, "risk": card.risk, "rule_id": card.rule_id,
        "reason_plain": card.reason_plain, "kb_cited": ", ".join(card.kb_ids),
        "drafted_reply": "", "send_mode": "", "firewall_status": "", "firewall_issue": "",
        "specificity_pass": None, "critic_issues": "", "repeat_contact": repeat, "mismatch": card.mismatch,
        "incident_id": "", "flags": ", ".join(dict.fromkeys(card.flags)),
        # extra (not in §9 sheet order, kept for app/eval)
        "summary_one_line": cls["summary_one_line"], "payment_id": ext["payment_id"],
        "base_risk": card.base_risk, "retrieval_score": None,
        "allowed_facts": json.dumps(card.allowed_facts, ensure_ascii=False),
    }


def write_outputs(rows: list):
    df = pd.DataFrame(rows)
    extra = [c for c in df.columns if c not in COLUMNS]
    df = df[COLUMNS + extra]
    summary = []
    for col in ["category", "action", "escalation_team", "risk", "send_mode"]:
        for k, v in df[col].value_counts(dropna=False).items():
            summary.append({"dimension": col, "value": k, "count": int(v)})
    with pd.ExcelWriter(OUT / "triage_results.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="results", index=False)
        pd.DataFrame(summary).to_excel(xw, sheet_name="summary", index=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-draft", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    tickets = load_tickets()
    merchants = load_merchants()
    kb = load_kb()
    repeat = repeat_contact_flags(tickets)
    recs = tickets.to_dict("records")

    with ThreadPoolExecutor(args.workers) as ex:
        classes = list(ex.map(lambda t: classify(t["merchant_message"]), recs))

    triaged = []
    for t, c in zip(recs, classes):
        ext, cls, merchant, card = triage(t, merchants, repeat[t["ticket_id"]], c)
        triaged.append((t, ext, cls, merchant, card))

    if args.no_draft:
        rows = [base_row(t, e, c, card, repeat[t["ticket_id"]]) for t, e, c, m, card in triaged]
    else:
        from copilot.draft import draft_and_guard
        from copilot.vectorstore import get_store
        store = get_store(kb, tickets)

        def work(item):
            t, e, c, m, card = item
            row = base_row(t, e, c, card, repeat[t["ticket_id"]])
            row.update(draft_and_guard(t, e, c, m, card, kb, store))
            return row
        with ThreadPoolExecutor(args.workers) as ex:
            rows = list(ex.map(work, triaged))
        from copilot.batch import run_batch
        rows = run_batch(rows, OUT)

    df = write_outputs(rows)
    print(f"Wrote {len(df)} rows -> outputs/triage_results.xlsx | LLM api_calls={STATS['api_calls']} "
          f"cache_hits={STATS['cache_hits']}")
    print(df["action"].value_counts().to_dict())
    if not args.no_draft:
        print(df["send_mode"].value_counts().to_dict())


if __name__ == "__main__":
    main()
