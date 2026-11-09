"""Copilot View building blocks: merchant profile, conversation, decision panel."""
import json

import pandas as pd
import streamlit as st

from . import charts
from .theme import C, esc, pill, risk_pill


def truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


STATUS_DOT = {"Settled": C["green"], "Delayed": C["amber"], "On hold": C["red"]}


def _kv(k, v, extra=""):
    v = "—" if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v
    return f'<div class="kv"><span>{esc(k)}{extra}</span><span class="num">{v if str(v).startswith("<") else esc(v)}</span></div>'


def merchant_card(row, merchants: pd.DataFrame, res: pd.DataFrame, key="mc"):
    with st.container(key=f"card_{key}"):
        mid = row.get("merchant_id")
        m = merchants[merchants.merchant_id == mid]
        if not mid or not len(m):
            st.markdown('<div class="card-t">Merchant</div>'
                        '<div class="empty"><i class="bi bi-person-x"></i>No merchant ID on this ticket.<br>'
                        'The copilot asks the merchant for it before looking anything up.</div>', unsafe_allow_html=True)
            return
        m = m.iloc[0]
        repeat = truthy(row.get("repeat_contact"))
        dot = STATUS_DOT.get(m.settlement_status, C["muted"])
        st.markdown(f"""
<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
 <div><div class="card-t" style="font-size:16px">{esc(m.business_name)}</div>
 <div class="card-s">{esc(m.segment)} · {esc(m.industry)} · {esc(m.city)}</div></div>
 <span class="mono sub">{esc(mid)}</span></div>
{pill('Repeat contact', kind='High', label='Repeat contact (4th+ ticket)') if repeat else ''}
<div class="lbl">Settlement</div>
{_kv('Status', f'<span class="dot" style="background:{dot}"></span>{esc(m.settlement_status)}')}
{_kv('Hold reason', f'<span class="internal" title="Never shown to the merchant">INTERNAL</span> {esc(m.hold_reason)}' if isinstance(m.hold_reason, str) else None)}
{_kv('Expected date', m.expected_settlement_date)}
{_kv('Last settlement', m.last_settlement_date)}
{_kv('Last amount', f'Rs {int(m.last_settlement_amount_inr):,}')}
<div class="lbl">Payments · 7-day success rate</div>""", unsafe_allow_html=True)
        st.plotly_chart(charts.mini_gauge(float(m.payment_success_rate_7d_pct)), config=charts.CONFIG,
                        key=f"g_{key}", width="stretch")
        st.markdown(f"""
{_kv('Open chargebacks', int(m.open_chargebacks))}
{_kv('Refunds in process', int(m.refunds_in_process))}
{_kv('KYC status', m.kyc_status)}
{_kv('GST invoice available', m.gst_invoice_available)}""", unsafe_allow_html=True)
        others = res[(res.merchant_id == mid) & (res.ticket_id != row.get("ticket_id"))].sort_values("created_at")
        items = "".join(
            f'<div class="mini"><span class="mono">{esc(o.ticket_id)}</span>'
            f'<span class="sub">{pd.Timestamp(o.created_at):%d %b}</span><span>{pill(o.action)}</span></div>'
            for o in others.itertuples())
        st.markdown(f'<div class="lbl">Other tickets from this merchant ({len(others)})</div>'
                    f'{items or "<div class=sub>None</div>"}', unsafe_allow_html=True)


def conversation(row, key="cv", live=False):
    tid = row.get("ticket_id")
    with st.container(key=f"card_{key}"):
        st.markdown('<div class="card-t">Conversation</div><div class="card-s">Merchant message and the AI-drafted reply</div>',
                    unsafe_allow_html=True)
        created = pd.Timestamp(row.get("created_at"))
        st.markdown(f"""
<div class="bubble in">{esc(row.get('merchant_message'))}</div>
<div class="bmeta"><i class="bi bi-person-circle"></i> {esc(row.get('merchant_id') or 'Unknown merchant')} · {esc(row.get('channel'))} · {created:%d %b %Y, %H:%M}</div>""",
                    unsafe_allow_html=True)
        reply = st.session_state.get(f"edit_{tid}", row.get("drafted_reply"))
        st.markdown(f"""
<div class="bubble out"><div class="ailbl"><i class="bi bi-stars"></i> AI draft · {esc(row.get('language'))}</div>{esc(reply)}</div>
<div class="bmeta r">Draft only — nothing is sent from this prototype</div>""", unsafe_allow_html=True)
        kbs = [k.strip() for k in str(row.get("kb_cited") or "").split(",") if k.strip()]
        kb_html = "".join(f'<span class="chip blue"><i class="bi bi-journal-text"></i> {esc(k)}</span>' for k in kbs)
        st.markdown(f'<div class="lbl">Knowledge base cited</div>{kb_html or "<span class=sub>No KB article (gap flagged)</span>"}',
                    unsafe_allow_html=True)
        if live:
            return
        st.markdown('<div class="lbl">Actions</div>', unsafe_allow_html=True)
        c = st.columns([1.5, 0.9, 1.1])
        if c[0].button("Approve & send", key=f"ap_{key}_{tid}", type="primary", width="stretch"):
            st.toast(f"{tid}: approved (demo: not actually sent)", icon=":material/check_circle:")
        if c[1].button("Edit", key=f"ed_{key}_{tid}", width="stretch"):
            st.session_state[f"editing_{tid}"] = True
        if c[2].button("Escalate", key=f"es_{key}_{tid}", width="stretch"):
            st.toast(f"{tid}: escalated to a specialist queue (session only)", icon=":material/outgoing_mail:")
        c = st.columns(3)
        for col, (lbl, msg) in zip(c, [("Make warmer", "warmer tone"), ("Hinglish", "Hinglish version"),
                                         ("Shorter", "shorter version")]):
            if col.button(lbl, key=f"{lbl}_{key}_{tid}", width="stretch"):
                st.toast(f"Rewrite requested: {msg} (demo: no API call)", icon=":material/auto_fix_high:")
        if st.session_state.get(f"editing_{tid}"):
            txt = st.text_area("Edit reply", value=reply, height=150, key=f"ta_{key}_{tid}")
            if st.button("Save edit", key=f"sv_{key}_{tid}", type="primary"):
                st.session_state[f"edit_{tid}"] = txt
                st.session_state[f"editing_{tid}"] = False
                st.toast("Edit saved for this session", icon=":material/edit:")
                st.rerun()


def steps(row):
    conf = float(row.get("confidence") or 0)
    critic = str(row.get("critic_issues") or "")
    fw_ok = row.get("firewall_status") == "PASS"
    spec_ok = truthy(row.get("specificity_pass"))
    is_threat = row.get("category") == "threat"
    mismatch = str(row.get("mismatch") or "")
    out = [
        ("Threat check", not is_threat,
         f"Threat language → {row.get('escalation_team')} team, acknowledgement only" if is_threat else "No legal, regulator, media or security threat"),
        ("Merchant ID", bool(row.get("merchant_id")),
         f"Found {row.get('merchant_id')}" if row.get("merchant_id") else "Missing — reply asks the merchant for it"),
        ("AI confidence", conf >= 0.8, f"{conf:.0%} (needs ≥ 80%)"),
        ("Records match", not mismatch, "Merchant's claim matches system data" if not mismatch else mismatch),
        ("Promise firewall", fw_ok, "No invented dates, amounts or promises" if fw_ok else row.get("firewall_issue")),
        ("Not-generic test", spec_ok, "Uses this merchant's own data" if spec_ok else "Reply too generic"),
    ]
    if is_threat:
        out.append(("Second-AI review", None, "Not needed — fixed acknowledgement template"))
    else:
        first = critic.split("; ")[0]
        more = critic.count("; ")
        short = (first[:150] + "…" if len(first) > 150 else first) + (f" (+{more} more)" if more else "")
        out.append(("Second-AI review", not critic, "Critic found no issues" if not critic else short))
    reasons = []
    if row.get("action") != "Auto-resolve":
        reasons.append(f"action is {row.get('action')}")
    if row.get("sentiment") == "angry":
        reasons.append("merchant is angry")
    if truthy(row.get("repeat_contact")):
        reasons.append("repeat contact")
    if mismatch:
        reasons.append("records mismatch")
    if critic:
        reasons.append("critic flagged issues")
    if not fw_ok:
        reasons.append("firewall blocked")
    auto = row.get("send_mode") == "AUTO_SEND"
    out.append(("Autonomy gate", auto, "All checks passed — safe to auto-send" if auto else "Human needed: " + ", ".join(reasons)))
    return out


def why_panel(row, key="why"):
    with st.container(key=f"card_{key}"):
        team = row.get("escalation_team")
        team_html = "" if team in (None, "", "None") else f'<span class="chip"><i class="bi bi-people"></i> {esc(team)}</span>'
        flags = [f for f in str(row.get("flags") or "").split(", ") if f]
        steps_html = ""
        for title, ok, detail in steps(row):
            cls = "na" if ok is None else ("ok" if ok else "bad")
            mark = "–" if ok is None else ("✓" if ok else "✗")
            steps_html += (f'<div class="step {"bad" if ok is False else ""}"><div class="ic {cls}">{mark}</div>'
                           f'<div><div class="st">{esc(title)}</div><div class="sd">{esc(detail)}</div></div></div>')
        mode = row.get("send_mode")
        fg, bg = {"AUTO_SEND": ("green", "green_soft"), "DO_NOT_SEND": ("red", "red_soft")}.get(mode, ("amber", "amber_soft"))
        st.markdown(f"""
<div class="card-t">Why this decision</div><div class="card-s">Rules decide; AI only reads and writes</div>
<div class="lbl">Summary</div><div style="font-size:13.5px">{esc(row.get('summary_one_line'))}</div>
<div class="lbl">Sentiment · Language</div>{pill(row.get('sentiment'))}{pill(row.get('language'), kind='Medium')}
<div class="lbl">Next step</div>{pill(row.get('action'))}{risk_pill(row.get('risk'))}{team_html}
<div class="lbl">Rule fired</div>
<div style="display:flex;gap:8px;align-items:flex-start"><span class="chip blue mono" style="margin:0">{esc(row.get('rule_id'))}</span>
<span style="font-size:13px">{esc(row.get('reason_plain'))}</span></div>
{('<div style="margin-top:8px">' + ''.join(f'<span class="chip">{esc(f)}</span>' for f in flags) + '</div>') if flags else ''}
<div class="lbl">Safety checks</div><div class="steps">{steps_html}</div>
<div class="final" style="background:{C[bg]};color:{C[fg]}"><span>Final send mode</span><span>{pill(mode)}</span></div>
""", unsafe_allow_html=True)


def live_row(t, ext, cls, card, out):
    """Build a results-style row from a live pipeline run (same shape as triage_results)."""
    from run_pipeline import base_row
    row = base_row(t, ext, cls, card, False)
    row.update(out)
    row["allowed_facts"] = json.dumps(card.allowed_facts)
    return row
