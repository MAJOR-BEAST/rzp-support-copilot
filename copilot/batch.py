"""Stage 4 batch: incidents (J7), KB gaps, would-not-send list."""
import pandas as pd

GAP_TITLES = {
    "api_unknown": "Troubleshooting intermittent API errors (5xx, timeouts, rate limits, blank checkout popup)",
    "tech_error_unknown": "Diagnosing unexplained payment errors at checkout",
    "unclear": "Triage script: questions to ask when the merchant's issue is unclear",
}


def find_incidents(df: pd.DataFrame) -> pd.DataFrame:
    """payment_failure tickets, sliding 24h window, >=3 distinct merchants -> incident. Flag only."""
    pf = df[(df["category"] == "payment_failure") & df["merchant_id"].notna()].sort_values("created_at")
    pf = pf.assign(created_at=pd.to_datetime(pf["created_at"]))
    assigned, incidents = set(), []
    recs = pf.to_dict("records")
    for i, r in enumerate(recs):
        if r["ticket_id"] in assigned:
            continue
        end = r["created_at"] + pd.Timedelta(hours=24)
        window = [x for x in recs[i:] if x["created_at"] <= end and x["ticket_id"] not in assigned]
        merchants = sorted({x["merchant_id"] for x in window})
        if len(merchants) >= 3:
            iid = f"INC-{len(incidents) + 1:03d}"
            for x in window:
                assigned.add(x["ticket_id"])
            incidents.append({
                "incident_id": iid, "window_start": window[0]["created_at"], "window_end": window[-1]["created_at"],
                "n_tickets": len(window), "n_merchants": len(merchants),
                "tickets": ", ".join(x["ticket_id"] for x in window), "merchants": ", ".join(merchants),
                "note": "Possible platform-wide payment degradation; flag only, per-ticket actions unchanged.",
            })
    return pd.DataFrame(incidents, columns=["incident_id", "window_start", "window_end", "n_tickets", "n_merchants",
                                            "tickets", "merchants", "note"])


def find_kb_gaps(df: pd.DataFrame, threshold: float = 0.35) -> pd.DataFrame:
    score = pd.to_numeric(df["retrieval_score"], errors="coerce")
    mask = df["flags"].fillna("").str.contains("kb_gap") | (score < threshold)
    gaps = df[mask]
    rows = []
    for sub, g in gaps.groupby("sub_intent"):
        rows.append({
            "sub_intent": sub, "n_tickets": len(g), "tickets": ", ".join(g["ticket_id"]),
            "max_retrieval_score": round(float(pd.to_numeric(g["retrieval_score"], errors="coerce").max()), 3),
            "suggested_article_title": GAP_TITLES.get(sub, f"New KB article: {sub.replace('_', ' ')}"),
            "example_message": g["merchant_message"].iloc[0],
        })
    return pd.DataFrame(rows, columns=["sub_intent", "n_tickets", "tickets", "max_retrieval_score",
                                       "suggested_article_title", "example_message"])


def run_batch(rows: list, out_dir) -> list:
    df = pd.DataFrame(rows)
    inc = find_incidents(df)
    inc.to_csv(out_dir / "incidents.csv", index=False, encoding="utf-8-sig")
    tmap = {t: r["incident_id"] for _, r in inc.iterrows() for t in r["tickets"].split(", ")}
    for row in rows:
        row["incident_id"] = tmap.get(row["ticket_id"], "")
    find_kb_gaps(df).to_csv(out_dir / "kb_gaps.csv", index=False, encoding="utf-8-sig")
    wns = df[df["firewall_status"] == "BLOCKED"][["ticket_id", "merchant_id", "rule_id", "action", "drafted_reply",
                                                 "firewall_issue"]]
    wns.rename(columns={"firewall_issue": "reason"}).to_csv(out_dir / "would_not_send.csv", index=False, encoding="utf-8-sig")
    return rows
