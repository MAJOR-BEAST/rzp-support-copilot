"""Merchant Support Copilot — Razorpay-style agent console (UI only; reads outputs/, live run is password-gated)."""
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from streamlit_option_menu import option_menu

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="Merchant Support Copilot", page_icon=":material/support_agent:",
                   layout="wide", initial_sidebar_state="expanded")

from ui import charts  # noqa: E402
from ui.copilot import conversation, live_row, merchant_card, steps, truthy, why_panel  # noqa: E402
from ui.theme import C, empty, esc, gap, kpi, pill, risk_pill, section, topnav  # noqa: E402
from ui.theme import inject  # noqa: E402

inject()

PAGES = ["Overview", "Ticket Queue", "Copilot View", "Guardrails", "Insights", "Evaluation", "Try a Ticket"]
ICONS = ["grid", "inbox", "chat-dots", "shield-check", "lightbulb", "bar-chart", "send"]


# ---------------------------------------------------------------- data
@st.cache_data
def load():
    res = pd.read_excel(OUT / "triage_results.xlsx", sheet_name="results", keep_default_na=False)
    res["created_at"] = pd.to_datetime(res["created_at"])
    read = lambda f: pd.read_csv(OUT / f, keep_default_na=False) if (OUT / f).exists() else pd.DataFrame()
    metrics = (OUT / "metrics.md").read_text(encoding="utf-8") if (OUT / "metrics.md").exists() else ""
    merchants = pd.read_excel(ROOT / "data" / "Buildathon_Student_Data_Pack.xlsx", sheet_name="P1_Merchants")
    return res, read("would_not_send.csv"), read("incidents.csv"), read("kb_gaps.csv"), read("mismatches.csv"), \
        metrics, merchants


if not (OUT / "triage_results.xlsx").exists():
    st.error("outputs/triage_results.xlsx not found. Run `python run_pipeline.py` first.")
    st.stop()

res, wns, inc, gaps, mism, metrics_md, merchants = load()
ss = st.session_state
ss.setdefault("tid", res.iloc[0]["ticket_id"])
ss.setdefault("qpage", 0)


def metric_pct(name):
    m = re.search(rf"^\| {re.escape(name)} \| \**([\d.]+)%", metrics_md, re.M)
    return float(m.group(1)) if m else None


def goto(page, tid=None):
    ss["goto"] = page
    if tid:
        ss["tid"] = tid


# deep links: ?page=Copilot%20View&tid=T-0016 (first load only)
if "qp_done" not in ss:
    ss["qp_done"] = True
    if st.query_params.get("page") in PAGES:
        ss["goto"] = st.query_params["page"]
    if st.query_params.get("tid") in set(res.ticket_id):
        ss["tid"] = st.query_params["tid"]

# ---------------------------------------------------------------- sidebar
# The current page lives in session state; option_menu only mirrors it (its own return value
# goes stale after a programmatic switch).
ss.setdefault("page", "Overview")
if "goto" in ss:
    ss["page"] = ss.pop("goto")


def _nav_changed(key):
    ss["page"] = ss[key]


with st.sidebar:
    option_menu(
        None, PAGES, icons=ICONS, default_index=0, manual_select=PAGES.index(ss["page"]), key="nav",
        on_change=_nav_changed,
        styles={
            "container": {"padding": "4px 0", "background-color": "#FFFFFF"},
            "icon": {"color": "inherit", "font-size": "16px"},
            "nav-link": {"font-size": "14px", "font-weight": "500", "color": "#0B1B3F", "padding": "10px 12px",
                         "border-radius": "10px", "margin": "2px 0", "--hover-color": "#F2F5FA",
                         "border-left": "3px solid transparent", "font-family": "Inter, sans-serif"},
            "nav-link-selected": {"background-color": "#EAF3FF", "color": "#1F7AE0", "font-weight": "600",
                                  "border-left": "3px solid #3395FF"},
        })
    page = ss["page"]
    st.markdown('<div class="side-h">Auto-send by category</div>', unsafe_allow_html=True)
    for c in sorted(res["category"].unique()):
        st.toggle(c.replace("_", " "), value=c != "threat", key=f"tg_{c}", disabled=c == "threat",
                  help="Display only. Threats can never be auto-sent.")
    st.markdown('<div class="side-foot">Built for Razorpay Campus AI Build-a-thon · Prototype, not an official '
                'Razorpay product. All merchant data is synthetic.</div>', unsafe_allow_html=True)

topnav()

n = len(res)
n_auto = int((res.send_mode == "AUTO_SEND").sum())
n_human = n - n_auto
n_esc = int((res.action == "Escalate").sum())
crit = re.search(r"Critical errors \| \*\*(\d+)\*\*", metrics_md)
crit = int(crit.group(1)) if crit else 0
act_acc = metric_pct("action")


# ---------------------------------------------------------------- pages
def page_overview():
    hour = datetime.now().hour
    greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    with st.container(key="hero"):
        c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="center")
        c1.markdown(f'<div class="hero"><h2>{greet}, Support team</h2><p>{n} tickets triaged · {n_auto} auto-sent · '
                    f'{n_human} need you · {crit} critical errors</p></div>', unsafe_allow_html=True)
        if c2.button("Open queue", key="h_q", width="stretch"):
            goto("Ticket Queue"); st.rerun()
        if c3.button("View guardrails", key="h_g", width="stretch"):
            goto("Guardrails"); st.rerun()
    gap()
    if len(inc):
        nm = len({m for s in inc["merchants"] for m in s.split(", ")})
        a1, a2 = st.columns([6, 1], vertical_alignment="center")
        a1.markdown(f'<div class="alert"><i class="bi bi-exclamation-octagon-fill"></i><div><b>Possible outage:</b> '
                    f'{len(inc)} incident windows — {nm} merchants reported payment failures within 24h of each other. '
                    f'Per-ticket actions are unchanged.</div></div>', unsafe_allow_html=True)
        if a2.button("View", key="al_v", width="stretch"):
            goto("Insights"); st.rerun()
        gap()
    k = st.columns(4)
    cards = [
        kpi("inboxes", "blue", n, "Total tickets", f"{res.created_at.dt.date.nunique()} days · 1–30 Sep 2026"),
        kpi("send-check", "green", f"{n_auto / n:.0%}", "Auto-send", f"<b>{n_auto}</b> replies safe to send"),
        kpi("arrow-up-right-circle", "red", n_esc, "Escalated to teams", f"{res[res.action == 'Escalate'].escalation_team.nunique()} specialist teams"),
        kpi("bullseye", "purple", f"{act_acc:.1f}%" if act_acc else "n/a", "Accuracy vs answer key (action)",
            f"<b>{crit}</b> critical errors"),
    ]
    for col, h in zip(k, cards):
        col.markdown(h, unsafe_allow_html=True)
    gap()
    r1 = st.columns([1, 1.25])
    with r1[0]:
        with st.container(key="card_donut"):
            st.markdown('<div class="card-t">Actions</div><div class="card-s">What the copilot decided per ticket</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(charts.donut_actions(res), config=charts.CONFIG, width="stretch")
    with r1[1]:
        with st.container(key="card_teams"):
            st.markdown('<div class="card-t">Escalations by team</div><div class="card-s">Where human specialists are needed</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(charts.bar_teams(res), config=charts.CONFIG, width="stretch")
    gap()
    r2 = st.columns([1, 1.25])
    with r2[0]:
        with st.container(key="card_heat"):
            st.markdown('<div class="card-t">Category × risk</div><div class="card-s">Ticket counts after risk modifiers</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(charts.heat_cat_risk(res), config=charts.CONFIG, width="stretch")
    with r2[1]:
        with st.container(key="card_daily"):
            st.markdown('<div class="card-t">Tickets per day</div><div class="card-s">Red dots mark detected payment incidents</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(charts.line_daily(res, inc), config=charts.CONFIG, width="stretch")


def page_queue():
    section("Ticket queue", "Every ticket with the copilot's decision. Open one to see the reasoning.")
    f1, f2 = st.columns([1.3, 3])
    q = f1.text_input("Search", placeholder="Ticket ID, merchant ID or text", label_visibility="collapsed", key="q_search")
    cats = f2.multiselect("Category", sorted(res.category.unique()), placeholder="All categories",
                          label_visibility="collapsed", key="q_cat")
    p = st.columns([1.3, 1.3, 0.75, 2.3])
    acts = p[0].pills("Action", ["Auto-resolve", "Ask for info", "Escalate"], selection_mode="multi", key="q_act")
    risks = p[1].pills("Risk", ["Critical", "High", "Medium", "Low"], selection_mode="multi", key="q_risk")
    modes = p[3].pills("Send mode", ["AUTO_SEND", "HUMAN_REVIEW", "DO_NOT_SEND", "HUMAN_WRITE"],
                       selection_mode="multi", key="q_mode",
                       format_func=lambda x: {"AUTO_SEND": "Auto-send", "HUMAN_REVIEW": "Human review",
                                              "DO_NOT_SEND": "Do not send", "HUMAN_WRITE": "Human write"}[x])
    langs = p[2].pills("Language", ["English", "Hinglish"], selection_mode="multi", key="q_lang",
                       format_func=lambda x: "EN" if x == "English" else "HI")
    v = res
    if q:
        ql = q.lower()
        v = v[v.ticket_id.str.lower().str.contains(ql) | v.merchant_id.astype(str).str.lower().str.contains(ql)
              | v.merchant_message.str.lower().str.contains(ql, regex=False)]
    for col, sel in [("category", cats), ("action", acts), ("risk", risks), ("send_mode", modes), ("language", langs)]:
        if sel:
            v = v[v[col].isin(sel)]
    per = 15
    pages = max(1, -(-len(v) // per))
    ss["qpage"] = min(ss["qpage"], pages - 1)
    gap()
    if not len(v):
        st.markdown(f'<div class="hcard">{empty("inbox", "No tickets match these filters.")}</div>', unsafe_allow_html=True)
        return
    hc = st.columns([9.3, 0.7])
    hc[0].markdown('<div class="qgrid qhead">' + "".join(f"<div>{h}</div>" for h in
                   ["Ticket", "Message", "Action", "Team", "Risk", "Send mode", "Lang"]) + "</div>",
                   unsafe_allow_html=True)
    for r in v.iloc[ss["qpage"] * per:(ss["qpage"] + 1) * per].itertuples():
        with st.container(key=f"qrow_{r.ticket_id}"):
            c = st.columns([9.3, 0.7], vertical_alignment="center")
            team = "—" if r.escalation_team == "None" else esc(r.escalation_team)
            c[0].markdown(f"""<div class="qgrid">
<div><span class="mono">{r.ticket_id}</span><span class="sub" style="display:block">{esc(r.merchant_id) or "no ID"}</span></div>
<div style="min-width:0"><span class="trunc" title="{esc(r.merchant_message)}">{esc(r.merchant_message)}</span>
<span class="sub">{r.category.replace("_", " ")} · {r.created_at:%d %b %H:%M}</span></div>
<div>{pill(r.action)}</div><div style="font-size:13px">{team}</div><div>{pill(r.risk)}</div>
<div>{pill(r.send_mode)}</div><div class="sub" style="font-weight:600">{"HI" if r.language == "Hinglish" else "EN"}</div>
</div>""", unsafe_allow_html=True)
            if c[1].button("View", key=f"v_{r.ticket_id}", width="stretch"):
                goto("Copilot View", r.ticket_id); st.rerun()
    gap()
    b = st.columns([1, 4, 1], vertical_alignment="center")
    if b[0].button("← Previous", disabled=ss["qpage"] == 0, key="qp", width="stretch"):
        ss["qpage"] -= 1; st.rerun()
    b[1].markdown(f'<div style="text-align:center;color:{C["muted"]};font-size:13px">'
                  f'Page {ss["qpage"] + 1} of {pages} · {len(v)} tickets</div>', unsafe_allow_html=True)
    if b[2].button("Next →", disabled=ss["qpage"] >= pages - 1, key="qn", width="stretch"):
        ss["qpage"] += 1; st.rerun()


def page_copilot():
    ids = list(res.ticket_id)
    i = ids.index(ss["tid"]) if ss["tid"] in ids else 0
    t = st.columns([1.3, 2.4, 0.9, 0.9], vertical_alignment="center")
    with t[0]:
        section("Copilot view", "Decision, reasoning and draft for one ticket")
    sel = t[1].selectbox("Ticket", ids, index=i, label_visibility="collapsed",
                         format_func=lambda x: f"{x} · {res.set_index('ticket_id').loc[x, 'merchant_message'][:70]}")
    if sel != ss["tid"]:
        ss["tid"] = sel; st.rerun()
    if t[2].button("← Prev ticket", disabled=i == 0, width="stretch"):
        ss["tid"] = ids[i - 1]; st.rerun()
    if t[3].button("Next ticket →", disabled=i == len(ids) - 1, width="stretch"):
        ss["tid"] = ids[i + 1]; st.rerun()
    row = res[res.ticket_id == ss["tid"]].iloc[0].to_dict()
    c = st.columns([1, 1.5, 1.15])
    with c[0]:
        merchant_card(row, merchants, res)
    with c[1]:
        conversation(row)
    with c[2]:
        why_panel(row)


def _highlight(text, issues):
    out = esc(text)
    for tok in re.findall(r"'([^']+)'", issues or ""):
        out = out.replace(esc(tok), f'<span class="hl">{esc(tok)}</span>')
    return out


def page_guardrails():
    section("Guardrails", "Four checks stand between an AI draft and a merchant")
    threats = int((res.category == "threat").sum())
    k = st.columns(4)
    for col, h in zip(k, [
        kpi("slash-circle", "red", len(wns), "Blocked drafts", "Promise firewall, final run"),
        kpi("person-check", "amber", n_human, "Sent to human review", f"{n_human / n:.0%} of tickets"),
        kpi("shield-exclamation", "purple", threats, "Threats caught", "Legal · Compliance · Security"),
        kpi("send-check", "green", f"{n_auto / n:.0%}", "Auto-send share", f"<b>{n_auto}</b> of {n}"),
    ]):
        col.markdown(h, unsafe_allow_html=True)
    gap()
    c = st.columns([1.15, 1])
    with c[0]:
        with st.container(key="card_blocked"):
            st.markdown('<div class="card-t">Blocked drafts</div><div class="card-s">Drafts the firewall refused to send, '
                        'offending phrase in red</div>', unsafe_allow_html=True)
            if len(wns):
                for r in wns.itertuples():
                    st.markdown(f'<div style="margin-bottom:14px"><span class="mono">{r.ticket_id}</span> '
                                f'<span class="chip">{esc(r.rule_id)}</span>'
                                f'<div class="bubble out" style="max-width:100%;margin-top:6px">{_highlight(r.drafted_reply, r.reason)}</div>'
                                + "".join(f'<span class="chip" style="color:{C["red"]};border-color:#F8C9CB;margin-top:6px">{esc(x)}</span>'
                                          for x in str(r.reason).split("; ")) + '</div>', unsafe_allow_html=True)
            else:
                st.markdown(empty("shield-check", "No final draft tripped the firewall in this run. Try the test bench "
                                  "to see it block an unsafe draft."), unsafe_allow_html=True)
        gap()
        with st.container(key="card_bench"):
            st.markdown('<div class="card-t">Firewall test bench</div><div class="card-s">Runs the real deterministic '
                        'firewall (no AI call) against a draft you write for any ticket</div>', unsafe_allow_html=True)
            from copilot.data_loader import load_kb
            from copilot.guardrails import firewall
            from copilot.rules import DecisionCard
            import json
            b1, b2 = st.columns([1, 2])
            tid = b1.selectbox("Ticket", list(res.ticket_id), index=list(res.ticket_id).index("T-0016"), key="fb_t")
            r = res[res.ticket_id == tid].iloc[0]
            b2.markdown(f'<div style="padding-top:30px">{pill(r.action)}{pill(r.rule_id, kind="Medium", label="Rule " + r.rule_id)}'
                        f'<span class="sub">{esc(r.reason_plain)}</span></div>', unsafe_allow_html=True)
            draft = st.text_area("Draft to check", key="fb_d", height=90,
                                 value="Good news! Your payout will be released within 72 hours and we guarantee "
                                       "it by 05 Oct 2026. — Razorpay Support")
            if st.button("Run firewall", type="primary", key="fb_run"):
                card = DecisionCard(r.category, r.sub_intent, r.action, r.escalation_team, r.risk, r.rule_id,
                                    [k.strip() for k in r.kb_cited.split(",") if k.strip()], json.loads(r.allowed_facts))
                kb = load_kb()
                status, issues = firewall(draft, card, [kb[k]["guidance"] for k in card.kb_ids + ["KB-16"] if k in kb])
                if status == "PASS":
                    st.markdown(f'{pill("AUTO_SEND", label="PASS")} <span class="sub">No invented facts or promises found.</span>',
                                unsafe_allow_html=True)
                else:
                    st.markdown(f'{pill("DO_NOT_SEND", label="BLOCKED")}<div class="bubble out" style="max-width:100%;margin-top:8px">'
                                f'{_highlight(draft, "; ".join(issues))}</div>'
                                + "".join(f'<span class="chip" style="color:{C["red"]};border-color:#F8C9CB;margin-top:8px">{esc(x)}</span>'
                                          for x in issues), unsafe_allow_html=True)
    with c[1]:
        with st.container(key="card_why_human"):
            st.markdown('<div class="card-t">Why tickets went to a human</div><div class="card-s">A ticket can have '
                        'several reasons</div>', unsafe_allow_html=True)
            reasons = {}
            for row in res.to_dict("records"):
                last = steps(row)[-1]
                if not last[1]:
                    for x in last[2].replace("Human needed: ", "").split(", "):
                        x = re.sub(r"action is ", "Action: ", x)
                        reasons[x] = reasons.get(x, 0) + 1
            s = pd.Series(reasons).sort_values()
            fig = go.Figure(go.Bar(x=s.values, y=s.index, orientation="h", marker_color=C["amber"], text=s.values,
                                   textposition="outside", cliponaxis=False, marker=dict(cornerradius=6)))
            fig.update_xaxes(visible=False)
            st.plotly_chart(charts._layout(fig, 300, bargap=.35), config=charts.CONFIG, width="stretch")
        gap()
        with st.container(key="card_rules"):
            st.markdown("""<div class="card-t">The four checks</div><div class="card-s">Applied to every AI draft</div>
<div class="steps">
<div class="step"><div class="ic ok"><i class="bi bi-shield-lock"></i></div><div><div class="st">Promise firewall</div><div class="sd">Every date, amount and duration must exist in the merchant's records or the cited KB. Blocks "72 hours", "approved", "waive", "guarantee"…</div></div></div>
<div class="step"><div class="ic ok"><i class="bi bi-fingerprint"></i></div><div><div class="st">Not-generic test</div><div class="sd">Reply must use this merchant's own data, or ask a direct question.</div></div></div>
<div class="step"><div class="ic ok"><i class="bi bi-eye"></i></div><div><div class="st">Second-AI review</div><div class="sd">A separate model checks tone, blame, leaked risk reasons, language and promises.</div></div></div>
<div class="step"><div class="ic ok"><i class="bi bi-sign-stop"></i></div><div><div class="st">Autonomy gate</div><div class="sd">Auto-send only for Auto-resolve, ≥80% confidence, calm merchant, first contacts and matching records.</div></div></div>
</div>""", unsafe_allow_html=True)


def page_insights():
    section("Insights", "Patterns across tickets that a single agent would miss")
    c = st.columns([1.1, 1])
    with c[0]:
        with st.container(key="card_inc"):
            st.markdown('<div class="card-t">Payment incidents</div><div class="card-s">≥3 merchants reporting payment '
                        'failures within 24h · flag only</div>', unsafe_allow_html=True)
            if len(inc):
                items = ""
                for r in inc.itertuples():
                    ws, we = pd.Timestamp(r.window_start), pd.Timestamp(r.window_end)
                    items += (f'<div class="tl-item"><div style="display:flex;gap:8px;align-items:center">'
                              f'<b>{r.incident_id}</b>{pill("Critical", label=f"{r.n_merchants} merchants")}'
                              f'<span class="sub">{ws:%d %b %H:%M} → {we:%d %b %H:%M}</span></div>'
                              f'<div style="margin-top:6px">' + "".join(f'<span class="chip mono">{t}</span>' for t in r.tickets.split(", "))
                              + f'</div><div class="sub">Merchants: {esc(r.merchants)}</div></div>')
                st.markdown(f'<div class="tl">{items}</div>', unsafe_allow_html=True)
            else:
                st.markdown(empty("activity", "No incidents detected."), unsafe_allow_html=True)
    with c[1]:
        with st.container(key="card_gaps"):
            st.markdown('<div class="card-t">Knowledge-base gaps</div><div class="card-s">Questions the KB cannot answer '
                        'today — suggested new articles</div>', unsafe_allow_html=True)
            if len(gaps):
                for r in gaps.itertuples():
                    st.markdown(f'<div style="border:1px solid {C["border"]};border-radius:12px;padding:14px;margin-bottom:10px">'
                                f'<div style="display:flex;justify-content:space-between;gap:8px"><span class="chip blue mono">{esc(r.sub_intent)}</span>'
                                f'<span class="sub">{r.n_tickets} tickets</span></div>'
                                f'<div style="font-weight:600;margin:8px 0 4px"><i class="bi bi-file-earmark-plus"></i> {esc(r.suggested_article_title)}</div>'
                                f'<div class="sub">e.g. “{esc(r.example_message)}”</div>'
                                f'<div style="margin-top:6px">' + "".join(f'<span class="chip mono">{t}</span>' for t in r.tickets.split(", "))
                                + '</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(empty("journal-check", "No KB gaps."), unsafe_allow_html=True)
        gap()
        with st.container(key="card_churn"):
            ch = res[res["flags"].str.contains("churn_risk")]
            st.markdown(f'<div class="card-t">Churn-risk merchants</div><div class="card-s">{len(ch)} tickets about pricing '
                        'or closure · routed to the Account Manager</div>', unsafe_allow_html=True)
            rows = ""
            for r in ch.itertuples():
                name = merchants.set_index("merchant_id").business_name.get(r.merchant_id, "")
                rows += (f'<div class="mini" style="align-items:center"><div style="flex:1;min-width:0"><b>{esc(name)}</b> '
                         f'<span class="mono sub">{r.merchant_id}</span>'
                         f'<div class="sub trunc">{esc(r.merchant_message)}</div></div>'
                         f'<span class="chip blue" style="margin:0"><i class="bi bi-bell"></i> Notify AM</span></div>')
            st.markdown(rows or empty("emoji-smile", "No churn signals."), unsafe_allow_html=True)


def page_eval():
    section("Evaluation", "Agent decisions compared with the answer key (150 tickets)")
    g = st.columns(4)
    for col, (name, label) in zip(g, [("category", "Category"), ("action", "Action"),
                                     ("escalation_team", "Team"), ("risk", "Risk")]):
        with col:
            with st.container(key=f"card_g_{name}"):
                st.plotly_chart(charts.gauge(metric_pct(name) or 0, f"{label} accuracy"), config=charts.CONFIG,
                                width="stretch")
    gap()
    c = st.columns([1, 1.4])
    with c[0]:
        st.markdown(f'<div class="hcard" style="background:{C["green_soft"]};border-color:#BDE8D6">'
                    f'<div style="display:flex;align-items:center;gap:14px"><div class="kpi-icon" style="background:#fff;color:{C["green"]}">'
                    f'<i class="bi bi-shield-fill-check"></i></div><div><div class="kpi-value" style="color:{C["green"]}">'
                    f'Critical errors: {crit}</div><div class="kpi-ctx">No threat auto-sent · no firewall bypass · '
                    f'no escalation auto-sent · no missed threat</div></div></div></div>', unsafe_allow_html=True)
        gap()
        with st.container(key="card_conf"):
            st.markdown('<div class="card-t">Action confusion matrix</div><div class="card-s">Rows: answer key · columns: agent</div>',
                        unsafe_allow_html=True)
            sec = re.search(r"## Action confusion matrix.*?\n\n(\|.*?)\n\n", metrics_md, re.S)
            if sec:
                lines = [l for l in sec.group(1).splitlines() if not re.match(r"^\|[-:| ]+\|$", l)]
                cells = [[x.strip() for x in l.strip("|").split("|")] for l in lines]
                conf = pd.DataFrame([[int(x) for x in r[1:]] for r in cells[1:]], index=[r[0] for r in cells[1:]],
                                    columns=cells[0][1:])
                st.plotly_chart(charts.confusion(conf), config=charts.CONFIG, width="stretch")
        st.markdown('<div class="sub" style="margin-top:12px"><i class="bi bi-info-circle"></i> Answer key = our hand-labelled '
                    'reference built from the written policy, not Razorpay\'s hidden labels.</div>', unsafe_allow_html=True)
    with c[1]:
        with st.container(key="card_mism"):
            st.markdown(f'<div class="card-t">Disagreements with the answer key</div><div class="card-s">{len(mism)} field '
                        f'differences across {mism.ticket_id.nunique() if len(mism) else 0} tickets</div>', unsafe_allow_html=True)
            if len(mism):
                body = "".join(
                    f'<tr><td class="mono">{r.ticket_id}</td><td>{esc(r.field)}</td>'
                    f'<td>{pill(r.expected, kind=r.expected if r.expected in ("Auto-resolve","Ask for info","Escalate","Low","Medium","High","Critical","AUTO_SEND","HUMAN_REVIEW") else "Low")}</td>'
                    f'<td>{pill(r.got, kind=r.got if r.got in ("Auto-resolve","Ask for info","Escalate","Low","Medium","High","Critical","AUTO_SEND","HUMAN_REVIEW") else "Medium")}</td>'
                    f'<td class="mono">{esc(r.rule_fired)}</td></tr>' for r in mism.itertuples())
                st.markdown(f'<table class="evt" style="width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed">'
                            f'<tr style="color:{C["muted"]};font-size:11px;text-transform:uppercase;text-align:left">'
                            f'<th style="padding:6px 4px">Ticket</th><th>Field</th><th>Expected</th><th>Got</th><th>Rule</th></tr>'
                            f'{body}</table>', unsafe_allow_html=True)
                st.markdown(f"""<div class="lbl">Reading the disagreements</div>
<div class="rd"><span class="mono">T-0013</span><span>Vague "Settlement issue" → copilot asks a question instead of answering (judgement call, safer side)</span></div>
<div class="rd"><span class="mono">T-0053</span><span>Second-AI review held a correct KYC reply for a human (over-cautious)</span></div>
<div class="rd"><span class="mono">T-0067</span><span>"Payment failed." → asked a clarifying question; key's sub-intent is not in the spec list</span></div>""",
                            unsafe_allow_html=True)
            else:
                st.markdown(empty("check2-all", "No disagreements."), unsafe_allow_html=True)
        gap()
        ok = int((res.send_mode == "AUTO_SEND").sum())
        st.markdown(f"""<div class="hcard"><div class="card-t">Headline numbers</div>
{''.join(f'<div class="kv"><span>{a}</span><span class="num">{b}</span></div>' for a, b in [
            ("Sub-intent accuracy", f"{metric_pct('sub_intent')}%"), ("Send-mode accuracy", f"{metric_pct('send_mode')}%"),
            ("Auto-send share", f"{ok / n:.1%} ({ok}/{n})"),
            ("Accuracy within auto-sent", re.search(r"within auto-sent \| ([\d.]+%)", metrics_md).group(1)),
            ("Specificity pass rate", re.search(r"Specificity pass rate: ([\d.]+%)", metrics_md).group(1)),
            ("Fact coverage", re.search(r"\*\*Fact coverage\*\*.*?: ([\d.]+% \(\d+/\d+)", metrics_md).group(1) + " tickets)")])}
</div>""", unsafe_allow_html=True)


SAMPLES = {
    "Settlement (Hinglish)": ("M1053", "Bhai settlement kab milega? Bank me kuch credit nahi hua."),
    "Payout on hold": ("M1024", "My payouts have been stopped since a few days. Dashboard shows something about a hold. Please release it."),
    "Legal threat": ("M1034", "If my money is not released today I will send a legal notice and approach consumer court."),
    "Big refund": ("M1009", "Please tell me the status of refund for pay_TESTREF12345, amount Rs 2,50,000, started 3 days back."),
    "Phishing?": ("M1015", "I got an SMS asking me to re-verify KYC by sharing OTP. Is this genuine?"),
    "No merchant ID": ("", "Mera paisa kaha hai??"),
}


def _apply_sample():
    s = ss.get("try_sample")
    if s:
        ss["try_mid"], ss["try_msg"] = SAMPLES[s][0] or "(none)", SAMPLES[s][1]


def page_try():
    section("Try a ticket", "Runs the full pipeline live: classifier → rules → retrieval → draft → guardrails")
    pw_expected = os.getenv("APP_PASSWORD")
    try:
        pw_expected = st.secrets.get("APP_PASSWORD", pw_expected)
    except Exception:
        pass
    c = st.columns([1, 1.6])
    with c[0]:
        with st.container(key="card_form"):
            st.markdown('<div class="card-t">New ticket</div><div class="card-s">Pick a sample or write your own</div>',
                        unsafe_allow_html=True)
            st.pills("Samples", list(SAMPLES), key="try_sample", on_change=_apply_sample, label_visibility="collapsed")
            ss.setdefault("try_mid", "M1053")
            ss.setdefault("try_msg", SAMPLES["Settlement (Hinglish)"][1])
            mids = ["(none)"] + list(merchants.merchant_id)
            st.selectbox("Merchant ID", mids, key="try_mid")
            st.selectbox("Channel", ["Email", "Chat", "Phone", "WhatsApp"], key="try_ch")
            st.text_area("Message", key="try_msg", height=120)
            pw = st.text_input("Password", type="password", key="try_pw") if pw_expected else None
            run = st.button("Run copilot", type="primary", width="stretch", key="try_run")
            st.markdown('<div class="sub" style="margin-top:8px"><i class="bi bi-lightning-charge"></i> Live call to the '
                        'Claude API · results for identical inputs come from cache.</div>', unsafe_allow_html=True)
        merchant_slot = st.container()
    if run:
        if pw_expected and pw != pw_expected:
            st.toast("Wrong password", icon=":material/lock:")
        else:
            from copilot.data_loader import load_kb, load_merchants
            from copilot.draft import draft_and_guard
            from copilot.vectorstore import get_store
            from run_pipeline import triage

            @st.cache_resource
            def _store():
                return get_store(load_kb())

            mid = None if ss["try_mid"] == "(none)" else ss["try_mid"]
            t = {"ticket_id": "LIVE", "created_at": pd.Timestamp.now(), "channel": ss["try_ch"],
                 "merchant_id": mid, "merchant_message": ss["try_msg"]}
            with st.spinner("Copilot is thinking…"):
                ext, cls, merchant, card = triage(t, load_merchants(), False)
                out = draft_and_guard(t, ext, cls, merchant, card, load_kb(), _store())
            ss["try_row"] = live_row(t, ext, cls, card, out)
            st.toast("Done", icon=":material/check_circle:")
    with c[1]:
        row = ss.get("try_row")
        if row:
            a, b = st.columns([1.35, 1])
            with a:
                conversation(row, key="tcv", live=True)
            with b:
                why_panel(row, key="twhy")
        else:
            st.markdown(f'<div class="hcard">{empty("send", "Run a ticket to see the decision, the reasoning and the draft here.")}</div>',
                        unsafe_allow_html=True)
    if ss.get("try_row") and ss["try_row"].get("merchant_id"):
        with merchant_slot:
            gap()
            merchant_card(ss["try_row"], merchants, res, key="tmc")


{"Overview": page_overview, "Ticket Queue": page_queue, "Copilot View": page_copilot, "Guardrails": page_guardrails,
 "Insights": page_insights, "Evaluation": page_eval, "Try a Ticket": page_try}[page or "Overview"]()
