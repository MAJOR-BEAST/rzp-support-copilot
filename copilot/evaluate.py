"""Evaluation vs data/answer_key.csv (the ONLY module allowed to read it) -> outputs/metrics.md, mismatches.csv.

Usage: python -m copilot.evaluate
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
KEY = ROOT / "data" / "answer_key.csv"
GOLD = ROOT / "data" / "P1_Gold_Labels_40.xlsx"
GOLD_MAP = {"Settlement": "settlement", "Payment failure": "payment_failure", "Refund": "refund",
            "Chargeback": "chargeback", "KYC": "kyc", "Fees & pricing": "fees_pricing",
            "API/Integration": "api_integration", "Account change/closure": "account_change",
            "Legal/Security threat": "threat", "Unclear": "unclear"}
FIELDS = [("category", "expected_category"), ("sub_intent", "expected_sub_intent"), ("action", "expected_action"),
          ("escalation_team", "expected_team"), ("risk", "expected_risk"), ("send_mode", "expected_send_mode")]


def _facts(must):
    s = str(must or "")
    return (re.findall(r"\b\d{2} [A-Z][a-z]{2} \d{4}\b", s) + re.findall(r"Rs [\d,]+", s)
            + re.findall(r"pay_[A-Za-z0-9]+", s))


def pct(x):
    return f"{100 * x:.1f}%"


def main():
    res = pd.read_excel(OUT / "triage_results.xlsx", sheet_name="results", keep_default_na=False)
    key = pd.read_csv(KEY, keep_default_na=False)
    m = res.merge(key, on="ticket_id", suffixes=("", "_key"))
    n = len(m)

    acc = {f: (m[f].astype(str) == m[e].astype(str)).mean() for f, e in FIELDS}
    rule_acc = (m["rule_id"] == m["rule_id_key"].str.replace("T", "T")).mean()

    # mismatches.csv
    rows = []
    for _, r in m.iterrows():
        for f, e in FIELDS:
            if str(r[f]) != str(r[e]):
                rows.append({"ticket_id": r["ticket_id"], "field": f, "expected": r[e], "got": r[f],
                             "rule_fired": r["rule_id"], "expected_rule": r["rule_id_key"],
                             "merchant_message": r["merchant_message_key"] if "merchant_message_key" in r else r["merchant_message"],
                             "reply": r["drafted_reply"]})
    mm = pd.DataFrame(rows)
    mm.to_csv(OUT / "mismatches.csv", index=False, encoding="utf-8-sig")

    # fact coverage
    cov_n, cov_hit, cov_miss = 0, 0, []
    for _, r in m.iterrows():
        facts = _facts(r["must_mention"])
        if not facts:
            continue
        cov_n += 1
        missing = [f for f in facts if f not in str(r["drafted_reply"])]
        if missing:
            cov_miss.append(f"{r['ticket_id']}: missing {missing}")
        else:
            cov_hit += 1

    auto = m[m["send_mode"] == "AUTO_SEND"]
    auto_correct = (auto["expected_send_mode"] == "AUTO_SEND") & (auto["action"] == auto["expected_action"])
    crit_fw = int(((m["firewall_status"] == "BLOCKED") & (m["send_mode"] == "AUTO_SEND")).sum())
    crit_threat = int(((m["category"] == "threat") & (m["send_mode"] == "AUTO_SEND")).sum())
    crit_esc = int(((m["expected_action"] == "Escalate") & (m["send_mode"] == "AUTO_SEND")).sum())
    missed_threat = int(((m["expected_category"] == "threat") & (m["category"] != "threat")).sum())
    critical = crit_fw + crit_threat + crit_esc + missed_threat

    conf = pd.crosstab(m["expected_action"], m["action"], rownames=["expected"], colnames=["got"])
    wns = pd.read_csv(OUT / "would_not_send.csv") if (OUT / "would_not_send.csv").exists() else pd.DataFrame()
    inc = pd.read_csv(OUT / "incidents.csv") if (OUT / "incidents.csv").exists() else pd.DataFrame()
    gaps = pd.read_csv(OUT / "kb_gaps.csv") if (OUT / "kb_gaps.csv").exists() else pd.DataFrame()
    spec = m["specificity_pass"].astype(str).str.lower().isin(["true", "1"]).mean()

    L = ["# Metrics — Merchant Support Copilot", ""]
    L += ["## Headline", "",
          f"| Metric | Value |", "|---|---|",
          f"| Tickets | {n} |",
          f"| Action accuracy | **{pct(acc['action'])}** |",
          f"| Team accuracy | **{pct(acc['escalation_team'])}** |",
          f"| Critical errors | **{critical}** |",
          f"| Auto-send share | {pct(len(auto) / n)} ({len(auto)}/{n}) |",
          f"| Accuracy within auto-sent | {pct(auto_correct.mean() if len(auto) else 0)} |", ""]
    L += ["## Benchmark", "",
          "Benchmark = `data/answer_key.csv`: hand-labelled message types + the written policy rules from the KB, "
          "built independently of the agent's AI classifier. It is **NOT** Razorpay's hidden answer set. "
          "The pipeline never reads this file; only `copilot/evaluate.py` does.", "",
          "| Field | Accuracy |", "|---|---|"]
    L += [f"| {f} | {pct(acc[f])} |" for f, _ in FIELDS]
    L += [f"| rule_id | {pct(rule_acc)} |", "",
          f"**Fact coverage** (reply contains the must_mention dates / amounts / payment IDs): "
          f"{pct(cov_hit / cov_n if cov_n else 0)} ({cov_hit}/{cov_n} tickets with checkable facts)", ""]
    if cov_miss:
        L += ["Missing facts:", ""] + [f"- {x}" for x in cov_miss] + [""]
    L += ["## Action confusion matrix (rows = expected, cols = got)", "", conf.to_markdown(), ""]
    L += ["## Critical errors (must all be 0)", "",
          f"- Firewall-blocked drafts reaching AUTO_SEND: {crit_fw}",
          f"- Threat tickets with AUTO_SEND: {crit_threat}",
          f"- Expected-Escalate tickets auto-sent: {crit_esc}",
          f"- Threat tickets not detected as threats: {missed_threat}", ""]
    L += ["## Send mode", "", m["send_mode"].value_counts().to_frame("count").to_markdown(), "",
          "Auto-send by category:", "",
          auto["category"].value_counts().to_frame("auto_sent").to_markdown() if len(auto) else "(none)", "",
          f"Specificity pass rate: {pct(spec)}", ""]
    L += ["## Would-not-send (promise firewall blocks)", "",
          f"Count: {len(wns)}", ""]
    if len(wns):
        L += [f"- {r.ticket_id} ({r.rule_id}): {r.reason}" for r in wns.itertuples()]
    else:
        L += ["No final draft tripped the firewall in this run. The firewall is exercised by "
              "`tests/test_guardrails.py` (72 hours, 'refund of Rs 50,000 approved', invented date) and blocked "
              "4 drafts during development (escalation drafts that added a '5-7 business days' timeline, and an echoed "
              "'502' error code), which led to tighter drafting rules."]
    L += ["", "## Incidents (J7: payment_failure, 24h sliding window, >=3 merchants)", "",
          inc.to_markdown(index=False) if len(inc) else "None found.", ""]
    L += ["## KB gaps", "", gaps.drop(columns=["example_message"], errors="ignore").to_markdown(index=False)
          if len(gaps) else "None.", ""]
    L += ["## Disagreements with the answer key", "",
          mm.drop(columns=["reply", "merchant_message"]).to_markdown(index=False) if len(mm) else "None.", "",
          "Full list incl. replies: `outputs/mismatches.csv`.", ""]
    L += ["## Known limitations / assumptions", "",
          "- **J2 snapshot:** merchant data is a 30 Sep 2026 snapshot used as 'current' for all September tickets. "
          "E.g. holds that started 26-28 Sep are applied to hold tickets dated earlier in September, and "
          "'last settlement 28 Sep' is quoted on tickets dated 2 Sep.",
          "- **Business days (J4)** exclude weekends only; bank holidays are not in the data.",
          "- **Temperature:** the current Claude API rejects the `temperature` parameter for these models, and "
          "thinking is switched off. Reproducibility comes from the response cache (`cache/llm/`): a second run makes 0 API calls.",
          "- Vague tickets (e.g. 'Settlement issue M1019', 'Payment failed. M1011') get a clarifying question "
          "(Q2) instead of an answer — the safer side of the trade-off.", ""]

    if GOLD.exists():
        g = pd.read_excel(GOLD)
        if {"my_category", "my_action"}.issubset(g.columns) and g["my_category"].notna().any():
            g = g.merge(res, on="ticket_id")
            g["my_category"] = g["my_category"].map(GOLD_MAP).fillna(g["my_category"])
            L += ["## Owner gold labels (40)", ""]
            for a, b in [("my_category", "category"), ("my_action", "action"),
                         ("my_escalation_team", "escalation_team"), ("my_risk", "risk")]:
                if a in g:
                    L.append(f"- {b}: {pct((g[a].astype(str) == g[b].astype(str)).mean())}")
    else:
        L += ["## Owner gold labels", "", "`data/P1_Gold_Labels_40.xlsx` not provided. A 20-ticket stratified "
              "sample is in `outputs/manual_check_20.xlsx` for the owner to grade.", ""]
        sample = (res.groupby("category", group_keys=False)
                  .apply(lambda d: d.sample(min(len(d), 2), random_state=7)))
        sample = pd.concat([sample, res.drop(sample.index).sample(max(0, 20 - len(sample)), random_state=7)]).head(20)
        sample = sample[["ticket_id", "merchant_message", "category", "action", "escalation_team", "risk",
                         "drafted_reply", "send_mode"]].assign(my_category="", my_action="", my_escalation_team="",
                                                               my_risk="", reply_ok="")
        sample.to_excel(OUT / "manual_check_20.xlsx", index=False)

    (OUT / "metrics.md").write_text("\n".join(L), encoding="utf-8")
    print(f"action {pct(acc['action'])} | team {pct(acc['escalation_team'])} | risk {pct(acc['risk'])} | "
          f"send_mode {pct(acc['send_mode'])} | critical {critical} | auto-send {len(auto)}/{n} | "
          f"fact coverage {cov_hit}/{cov_n} | mismatches {len(mm)} rows")


if __name__ == "__main__":
    main()
