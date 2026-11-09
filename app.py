"""Merchant Support Copilot — agent console. Loads outputs/ only (no API cost) except the password-gated 'Try a ticket'."""
import html
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="Merchant Support Copilot", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select { font-family: 'Inter', sans-serif !important; }
.stApp { background: #F3F6FB; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.2rem; }
.topbar { background: #072654; color: #fff; padding: 18px 28px; border-radius: 10px; margin-bottom: 18px; }
.topbar h1 { color: #fff; font-size: 1.5rem; font-weight: 700; margin: 0; padding: 0; }
.topbar p { color: #B9C6DA; font-size: .85rem; margin: 4px 0 0 0; }
.card { background: #fff; border: 1px solid #E3E8F0; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(7,38,84,.06); margin-bottom: 14px; }
.kpi .label { color: #64748B; font-size: .78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.kpi .value { color: #072654; font-size: 1.8rem; font-weight: 700; margin-top: 4px; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .72rem; font-weight: 600;
        font-variant: small-caps; letter-spacing: .03em; margin-right: 6px; text-transform: lowercase; }
.sec { color: #64748B; font-size: .75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; margin: 10px 0 4px; }
.reply { background: #F8FAFD; border-left: 3px solid #3395FF; padding: 12px 14px; border-radius: 6px; white-space: pre-wrap; }
.stButton > button[kind="primary"], .stButton > button { background: #3395FF; color: #fff; border: 0; border-radius: 8px; font-weight: 600; }
.stButton > button:hover { background: #1F7AE0; color: #fff; }
section[data-testid="stSidebar"] { background: #072654; }
section[data-testid="stSidebar"] * { color: #fff; }
section[data-testid="stSidebar"] [data-baseweb="select"] * { color: #072654; }
section[data-testid="stSidebar"] [data-baseweb="tag"] { background: #3395FF !important; }
section[data-testid="stSidebar"] [data-baseweb="tag"] * { color: #fff !important; }
.stTabs [aria-selected="true"] { color: #3395FF !important; }
</style>
<div class="topbar"><h1>Merchant Support Copilot</h1><p>Prototype · Razorpay Campus AI Build-a-thon</p></div>
""", unsafe_allow_html=True)

ACTION_STYLE = {"Auto-resolve": ("#0E9F6E", "#E7F7F1"), "Ask for info": ("#6B4EFF", "#EFEBFF"),
                "Escalate": ("#E5484D", "#FDECEC")}
RISK_STYLE = {"Critical": ("#E5484D", "#FDECEC"), "High": ("#F59E0B", "#FEF3E2"), "Medium": ("#3395FF", "#EAF3FF"),
              "Low": ("#64748B", "#F1F4F8")}
SEND_STYLE = {"AUTO_SEND": ("#0E9F6E", "#E7F7F1"), "HUMAN_REVIEW": ("#F59E0B", "#FEF3E2"),
              "DO_NOT_SEND": ("#E5484D", "#FDECEC"), "HUMAN_WRITE": ("#6B4EFF", "#EFEBFF")}
SENT_STYLE = {"calm": ("#0E9F6E", "#E7F7F1"), "frustrated": ("#F59E0B", "#FEF3E2"), "angry": ("#E5484D", "#FDECEC")}


def pill(text, style_map):
    fg, bg = style_map.get(str(text), ("#64748B", "#F1F4F8"))
    return f'<span class="pill" style="color:{fg};background:{bg}">{html.escape(str(text))}</span>'


@st.cache_data
def load():
    res = pd.read_excel(OUT / "triage_results.xlsx", sheet_name="results", keep_default_na=False)
    read = lambda f: pd.read_csv(OUT / f, keep_default_na=False) if (OUT / f).exists() else pd.DataFrame()
    metrics = (OUT / "metrics.md").read_text(encoding="utf-8") if (OUT / "metrics.md").exists() else ""
    merchants = pd.read_excel(ROOT / "data" / "Buildathon_Student_Data_Pack.xlsx", sheet_name="P1_Merchants")
    return res, read("would_not_send.csv"), read("incidents.csv"), read("kb_gaps.csv"), metrics, merchants


if not (OUT / "triage_results.xlsx").exists():
    st.error("outputs/triage_results.xlsx not found. Run `python run_pipeline.py` first.")
    st.stop()

res, wns, inc, gaps, metrics_md, merchants = load()
res["created_at"] = pd.to_datetime(res["created_at"])

# ---------------- sidebar ----------------
with st.sidebar:
    st.markdown("### Filters")
    filt = {}
    for col, label in [("category", "Category"), ("action", "Action"), ("escalation_team", "Team"),
                       ("risk", "Risk"), ("send_mode", "Send mode")]:
        filt[col] = st.multiselect(label, sorted(res[col].unique()))
    st.markdown("### Auto-send toggles")
    st.caption("Display only — mirrors CATEGORY_AUTO_SEND in guardrails.py")
    for c in sorted(res["category"].unique()):
        st.toggle(c, value=c != "threat", key=f"tg_{c}", disabled=c == "threat")
    st.markdown("### Counts")
    for col in ["action", "send_mode"]:
        for k, v in res[col].value_counts().items():
            st.markdown(f"{k}: **{v}**")

view = res.copy()
for col, vals in filt.items():
    if vals:
        view = view[view[col].isin(vals)]

m = re.search(r"Action accuracy \| \*\*([\d.]+%)\*\*", metrics_md)
acc_txt = m.group(1) if m else "n/a"

tabs = st.tabs(["Queue", "Would not send", "Incidents", "KB gaps", "Metrics", "Try a ticket"])

# ---------------- Queue ----------------
with tabs[0]:
    k = st.columns(4)
    kpis = [("Total tickets", len(res)), ("Auto-send %", f"{(res.send_mode == 'AUTO_SEND').mean() * 100:.0f}%"),
            ("Escalated", int((res.action == "Escalate").sum())), ("Accuracy vs answer key", acc_txt)]
    for col, (lab, val) in zip(k, kpis):
        col.markdown(f'<div class="card kpi"><div class="label">{lab}</div><div class="value">{val}</div></div>',
                     unsafe_allow_html=True)

    show = view[["ticket_id", "created_at", "merchant_id", "category", "action", "escalation_team", "risk",
                 "send_mode", "merchant_message"]]
    st.markdown(f'<div class="sec">Queue · {len(view)} tickets</div>', unsafe_allow_html=True)
    ev = st.dataframe(show, hide_index=True, width="stretch", height=320, on_select="rerun",
                      selection_mode="single-row", key="queue")
    sel = ev.selection.rows if ev and ev.selection else []
    tid = show.iloc[sel[0]]["ticket_id"] if sel else (show.iloc[0]["ticket_id"] if len(show) else None)

    if tid:
        r = res[res.ticket_id == tid].iloc[0]
        left, right = st.columns([1, 1.3])
        with left:
            st.markdown(f"""<div class="card">
<div class="sec">Ticket {r.ticket_id} · {r.channel} · {r.created_at:%d %b %Y %H:%M}</div>
<div style="font-size:1rem">{html.escape(r.merchant_message)}</div>
<div class="sec">Summary</div><div>{html.escape(str(r.summary_one_line))}</div>
<div class="sec">Sentiment · Language</div>{pill(r.sentiment, SENT_STYLE)}{pill(r.language, {})}
<div class="sec">Flags</div><div>{html.escape(str(r['flags'])) or '—'}{(' · ' + r.incident_id) if r.incident_id else ''}</div>
</div>""", unsafe_allow_html=True)
            mrow = merchants[merchants.merchant_id == r.merchant_id]
            if len(mrow):
                mr = mrow.iloc[0]
                facts = {"Business": mr.business_name, "Segment": mr.segment, "Settlement status": mr.settlement_status,
                         "Hold reason (internal)": mr.hold_reason, "Last settlement": f"{mr.last_settlement_date} · Rs {int(mr.last_settlement_amount_inr):,}",
                         "Expected settlement": mr.expected_settlement_date, "Success rate 7d": f"{mr.payment_success_rate_7d_pct}%",
                         "Open chargebacks": mr.open_chargebacks, "KYC": mr.kyc_status}
                rows_html = "".join(f"<tr><td style='color:#64748B;padding:2px 12px 2px 0'>{a}</td><td>{'—' if pd.isna(b) else html.escape(str(b))}</td></tr>"
                                    for a, b in facts.items())
                st.markdown(f'<div class="card"><div class="sec">Merchant {r.merchant_id}</div><table>{rows_html}</table></div>',
                            unsafe_allow_html=True)
            else:
                st.markdown('<div class="card"><div class="sec">Merchant</div>No merchant ID on ticket.</div>',
                            unsafe_allow_html=True)
        with right:
            team = "" if r.escalation_team in ("None", "") else f" → {html.escape(r.escalation_team)}"
            st.markdown(f"""<div class="card">
<div class="sec">Next step</div>{pill(r.action, ACTION_STYLE)}{pill(r.risk + ' risk', {r.risk + ' risk': RISK_STYLE[r.risk]})}{pill(r.send_mode, SEND_STYLE)}
<div style="margin-top:6px"><b>{html.escape(r.action)}{team}</b> · rule {r.rule_id} · confidence {r.confidence}</div>
<div style="color:#475569">{html.escape(r.reason_plain)}</div>
<div class="sec">Drafted reply</div><div class="reply">{html.escape(st.session_state.get(f'edit_{tid}', r.drafted_reply))}</div>
<div class="sec">KB cited · retrieved</div><div>{r.kb_cited or '—'} · {r.get('kb_retrieved', '')} (top score {r.retrieval_score})</div>
<div class="sec">Guardrails</div>
<div>Firewall: <b>{r.firewall_status}</b> {html.escape(r.firewall_issue)} · Specificity: <b>{r.specificity_pass}</b></div>
<div>Critic: {html.escape(r.critic_issues) or 'pass'}</div>
</div>""", unsafe_allow_html=True)
            b1, b2, b3 = st.columns(3)
            state = st.session_state.setdefault("decisions", {})
            if b1.button("Approve", key=f"ap_{tid}", width="stretch"):
                state[tid] = "Approved"
            if b2.button("Edit", key=f"ed_{tid}", width="stretch"):
                st.session_state[f"editing_{tid}"] = True
            if b3.button("Escalate", key=f"es_{tid}", width="stretch"):
                state[tid] = "Escalated by agent"
            if st.session_state.get(f"editing_{tid}"):
                txt = st.text_area("Edit reply", value=st.session_state.get(f"edit_{tid}", r.drafted_reply), height=160)
                if st.button("Save edit", key=f"sv_{tid}"):
                    st.session_state[f"edit_{tid}"] = txt
                    st.session_state[f"editing_{tid}"] = False
                    state[tid] = "Edited"
                    st.rerun()
            if tid in state:
                st.success(f"{tid}: {state[tid]} (session only)")

# ---------------- other tabs ----------------
with tabs[1]:
    st.markdown('<div class="sec">Drafts blocked by the promise firewall</div>', unsafe_allow_html=True)
    if len(wns):
        st.dataframe(wns, hide_index=True, width="stretch")
    else:
        st.info("No final draft was blocked in this run. Firewall behaviour is covered by tests/test_guardrails.py.")
    dns = res[res.send_mode.isin(["DO_NOT_SEND", "HUMAN_WRITE"])]
    if len(dns):
        st.dataframe(dns[["ticket_id", "rule_id", "send_mode", "firewall_issue", "drafted_reply"]], hide_index=True)
with tabs[2]:
    st.markdown('<div class="sec">Payment-failure clusters · 24h window · ≥3 merchants (flag only)</div>',
                unsafe_allow_html=True)
    if len(inc):
        st.dataframe(inc, hide_index=True, width="stretch")
    else:
        st.info("No incidents.")
with tabs[3]:
    st.markdown('<div class="sec">Knowledge-base gaps</div>', unsafe_allow_html=True)
    if len(gaps):
        st.dataframe(gaps, hide_index=True, width="stretch")
    else:
        st.info("No KB gaps.")
with tabs[4]:
    st.markdown(metrics_md)

# ---------------- Try a ticket (live, password) ----------------
with tabs[5]:
    try:
        pw_expected = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        pw_expected = None
    pw_expected = pw_expected or os.getenv("APP_PASSWORD")
    pw = st.text_input("Password", type="password")
    if not pw_expected or pw != pw_expected:
        st.caption("Runs the full pipeline live with the Claude API. Enter the password to enable.")
    else:
        msg = st.text_area("Merchant message", "Bhai settlement kab milega? Bank me kuch credit nahi hua.")
        mid = st.text_input("Merchant ID (optional)", "M1053")
        if st.button("Run pipeline"):
            from copilot.data_loader import load_kb, load_merchants
            from copilot.draft import draft_and_guard
            from copilot.vectorstore import get_store
            from run_pipeline import triage

            @st.cache_resource
            def _store():
                return get_store(load_kb())

            t = {"ticket_id": "LIVE", "created_at": pd.Timestamp.now(), "channel": "Console",
                 "merchant_id": mid.strip() or None, "merchant_message": msg}
            with st.spinner("Classifying, applying policy, drafting, checking guardrails..."):
                ext, cls, merchant, card = triage(t, load_merchants(), False)
                out = draft_and_guard(t, ext, cls, merchant, card, load_kb(), _store())
            team = "" if card.team == "None" else f" → {card.team}"
            st.markdown(f"""<div class="card">{pill(card.action, ACTION_STYLE)}{pill(card.risk + ' risk', {card.risk + ' risk': RISK_STYLE[card.risk]})}{pill(out['send_mode'], SEND_STYLE)}
<div style="margin-top:6px"><b>{card.category} / {card.sub_intent}{team}</b> · rule {card.rule_id} · confidence {cls['confidence']} · {cls['sentiment']} · {cls['language']}</div>
<div style="color:#475569">{html.escape(card.reason_plain)}</div>
<div class="sec">Drafted reply</div><div class="reply">{html.escape(out['drafted_reply'])}</div>
<div class="sec">Guardrails</div><div>Firewall: <b>{out['firewall_status']}</b> {html.escape(out['firewall_issue'])} · Critic: {html.escape(out['critic_issues']) or 'pass'}</div>
</div>""", unsafe_allow_html=True)
