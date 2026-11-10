"""Design tokens, global CSS, pills and shell HTML for the Razorpay-style console."""
import base64
import html
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent

C = {
    "navy": "#072654", "blue": "#3395FF", "blue_dark": "#1F7AE0", "blue_soft": "#EAF3FF",
    "bg": "#F2F5FA", "card": "#FFFFFF", "border": "#E3E8F0", "text": "#0B1B3F", "muted": "#64748B",
    "green": "#0E9F6E", "green_soft": "#E7F7F1", "purple": "#6B4EFF", "purple_soft": "#EFEBFF",
    "red": "#E5484D", "red_soft": "#FDECEC", "amber": "#F59E0B", "amber_soft": "#FEF5E7",
    "grey_soft": "#F1F4F8",
}

PILL = {
    # actions
    "Auto-resolve": ("green", "green_soft"), "Ask for info": ("purple", "purple_soft"), "Escalate": ("red", "red_soft"),
    # risk
    "Critical": ("red", "red_soft"), "High": ("amber", "amber_soft"), "Medium": ("blue", "blue_soft"),
    "Low": ("muted", "grey_soft"),
    # send mode
    "AUTO_SEND": ("green", "green_soft"), "HUMAN_REVIEW": ("amber", "amber_soft"), "DO_NOT_SEND": ("red", "red_soft"),
    "HUMAN_WRITE": ("purple", "purple_soft"),
    # sentiment
    "calm": ("green", "green_soft"), "frustrated": ("amber", "amber_soft"), "angry": ("red", "red_soft"),
}
SEND_LABEL = {"AUTO_SEND": "Auto-send", "HUMAN_REVIEW": "Human review", "DO_NOT_SEND": "Do not send",
              "HUMAN_WRITE": "Human write"}


def pill(text, kind=None, label=None):
    fg, bg = PILL.get(kind or str(text), ("muted", "grey_soft"))
    return (f'<span class="pill" style="color:{C[fg]};background:{C[bg]}">'
            f'{html.escape(str(label or SEND_LABEL.get(str(text), text)))}</span>')


def risk_pill(risk):
    return pill(risk, label=f"{risk} risk")


def esc(s):
    return html.escape("" if s is None else str(s))


@st.cache_data
def logo_data_uri():
    svg = (ROOT / "assets" / "razorpay-logo.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');
@import url('https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css');
:root{
 --rzp-navy:#072654;--rzp-blue:#3395FF;--rzp-blue-dark:#1F7AE0;--rzp-blue-soft:#EAF3FF;
 --bg:#F2F5FA;--card:#FFFFFF;--border:#E3E8F0;--text:#0B1B3F;--muted:#64748B;
 --green:#0E9F6E;--green-soft:#E7F7F1;--purple:#6B4EFF;--purple-soft:#EFEBFF;
 --red:#E5484D;--red-soft:#FDECEC;--amber:#F59E0B;--amber-soft:#FEF5E7;
 --shadow:0 1px 2px rgba(16,24,40,.06);--shadow-hover:0 8px 20px rgba(16,24,40,.10);
}
html,body,.stApp,[class*="css"],button,input,textarea,select,.stMarkdown,p,div,span,label{font-family:'Inter',sans-serif;}
.bi{font-family:'bootstrap-icons' !important;}
.stApp{background:var(--bg);color:var(--text);}
.num,.kpi-value,td.num{font-variant-numeric:tabular-nums;}
/* hide streamlit chrome */
#MainMenu,footer,[data-testid="stDecoration"],[data-testid="stStatusWidget"],[data-testid="stMainMenu"],
.stDeployButton,[data-testid="stAppDeployButton"],[data-testid="stToolbarActions"]{display:none !important;}
header[data-testid="stHeader"]{background:transparent;height:0;}
/* reopen-sidebar tab: Streamlit's own expand button, pinned to the middle of the left edge */
[data-testid="stExpandSidebarButton"]{position:fixed !important;left:0;top:50%;transform:translateY(-50%);z-index:999990;
 width:30px;height:72px;display:flex !important;align-items:center;justify-content:center;background:#fff !important;
 border:1px solid var(--border) !important;border-left:0 !important;border-radius:0 12px 12px 0 !important;
 box-shadow:0 4px 14px rgba(16,24,40,.12);cursor:pointer;transition:width 150ms ease,background 150ms ease;}
[data-testid="stExpandSidebarButton"]:hover{width:36px;background:var(--rzp-blue-soft) !important;}
[data-testid="stExpandSidebarButton"] span{color:var(--rzp-blue) !important;}
/* top nav (keyed container) */
.st-key-topnav{background:#fff;border:1px solid var(--border);border-radius:14px;padding:0 20px;margin-bottom:24px;
 box-shadow:var(--shadow);min-height:60px;display:flex;flex-direction:column;justify-content:center;}
.st-key-topnav [data-testid="stHorizontalBlock"]{align-items:center;flex-wrap:nowrap;}
.st-key-topnav [data-testid="stElementContainer"],.st-key-topnav [data-testid="stMarkdown"],
.st-key-topnav [data-testid="stMarkdownContainer"],.st-key-topnav [data-testid="stVerticalBlock"]{margin:0 !important;gap:0 !important;}
.st-key-topnav [data-testid="stMarkdownContainer"] p{margin:0;}
.st-key-logo_home button{background:url("__LOGO__") left center/contain no-repeat !important;border:0 !important;
 width:118px;height:28px;min-height:28px;padding:0 !important;color:transparent !important;font-size:0 !important;
 box-shadow:none !important;cursor:pointer;}
.st-key-logo_home button:hover{opacity:.8;}
.st-key-logo_home button p{font-size:0 !important;}
.flowlink{display:flex;align-items:center;gap:10px;margin:14px 0 4px;padding:12px 14px;border:1px solid #CFE3FF;border-radius:12px;
 background:var(--rzp-blue-soft);color:var(--rzp-blue-dark) !important;text-decoration:none !important;font-size:13.5px;font-weight:600;
 transition:background 150ms ease;}
.flowlink:hover{background:#DCEBFF;}
.flowlink i{font-size:18px;} .flowlink small{display:block;font-weight:500;color:var(--muted);font-size:11.5px;}
section[data-testid="stSidebar"] .flowlink *{color:inherit;}
/* sidebar flowchart section */
.st-key-side_flow{margin-top:14px;padding:14px;border:1px solid #CFE3FF;border-radius:14px;
 background:linear-gradient(160deg,#F5F9FF 0%,#EAF3FF 100%);gap:10px;}
.st-key-side_flow [data-testid="stElementContainer"],.st-key-side_flow [data-testid="stMarkdown"],
.st-key-side_flow [data-testid="stMarkdownContainer"]{margin:0 !important;height:auto !important;}
.sf-h{display:flex;align-items:center;gap:10px;margin-bottom:4px;}
.sf-h b{display:block;font-size:13.5px;color:var(--text);}
.sf-h small{display:block;font-size:11.5px;color:var(--muted);line-height:1.35;margin-top:1px;}
.sf-ic{width:34px;height:34px;flex:0 0 34px;border-radius:10px;background:var(--rzp-navy);color:#fff;display:flex;
 align-items:center;justify-content:center;font-size:16px;}
.sf-lock{margin-left:auto;color:var(--rzp-blue-dark);font-size:14px;}
.sf-link{font-size:12px;color:var(--rzp-blue-dark) !important;text-decoration:none !important;font-weight:500;}
.sf-link:hover{text-decoration:underline !important;}
.block-container{padding-top:1rem !important;padding-bottom:2rem;max-width:100% !important;padding-left:1.5rem;padding-right:1.5rem;}
/* sidebar */
section[data-testid="stSidebar"]{background:#FFFFFF;border-right:1px solid var(--border);}
section[data-testid="stSidebar"] > div{padding-top:.5rem;}
section[data-testid="stSidebar"] iframe{border:0;}
.side-foot{font-size:11.5px;color:var(--muted);line-height:1.45;margin-top:10px;padding-top:12px;border-top:1px solid var(--border);}
.side-h{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px;}
/* top nav */
.topnav{display:flex;align-items:center;gap:16px;background:#fff;height:60px;border:1px solid var(--border);
 border-radius:14px;padding:0 20px;margin-bottom:24px;box-shadow:var(--shadow);}
.topnav img{height:24px;display:block;}
.topnav .div{width:1px;height:26px;background:var(--border);}
.topnav .prod{font-weight:600;font-size:15px;color:var(--text);white-space:nowrap;}
.topnav .search{flex:1;display:flex;justify-content:center;}
.topnav .search div{width:min(420px,100%);display:flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--border);
 border-radius:10px;padding:7px 12px;color:var(--muted);font-size:13px;}
.topnav .right{display:flex;align-items:center;gap:12px;}
.avatar{width:34px;height:34px;border-radius:50%;background:var(--rzp-navy);color:#fff;display:flex;align-items:center;
 justify-content:center;font-weight:600;font-size:13px;}
/* section headers */
.sh{margin:0 0 12px 0;} .sh h3{font-size:18px;font-weight:700;color:var(--text);margin:0;padding:0;}
.sh p{font-size:13px;color:var(--muted);margin:2px 0 0 0;}
.gap{height:24px;}
/* cards: keyed containers st-key-card* */
[class*="st-key-card"]{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px;
 box-shadow:var(--shadow);transition:transform 150ms ease,box-shadow 150ms ease;}
[class*="st-key-card"]:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover);}
.hcard{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px;box-shadow:var(--shadow);
 transition:transform 150ms ease,box-shadow 150ms ease;height:100%;}
.hcard:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover);}
.card-t{font-size:14px;font-weight:600;color:var(--text);margin-bottom:2px;}
.card-s{font-size:12px;color:var(--muted);margin-bottom:10px;}
/* KPI */
.kpi{display:flex;flex-direction:column;gap:6px;}
.kpi-icon{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;}
.kpi-value{font-size:28px;font-weight:700;color:var(--text);line-height:1.1;margin-top:6px;}
.kpi-label{font-size:13px;color:var(--muted);font-weight:500;}
.kpi-ctx{font-size:12px;color:var(--muted);}
.kpi-ctx b{color:var(--green);font-weight:600;}
/* hero */
.st-key-hero{position:relative;overflow:hidden;border-radius:16px;padding:28px 30px;color:#fff;
 background:linear-gradient(135deg,#072654 0%,#1F4FB8 55%,#3395FF 100%);box-shadow:var(--shadow);}
.st-key-hero::before{content:"";position:absolute;width:260px;height:260px;border-radius:50%;background:rgba(255,255,255,.07);
 right:-60px;top:-120px;}
.st-key-hero::after{content:"";position:absolute;width:180px;height:180px;border-radius:50%;background:rgba(255,255,255,.06);
 right:220px;bottom:-110px;}
.st-key-hero [data-testid="stHorizontalBlock"]{align-items:center;position:relative;z-index:1;}
.hero h2{color:#fff;font-size:24px;font-weight:700;margin:0 0 6px;padding:0;}
.hero p{color:#D6E4FF;font-size:14px;margin:0;}
.st-key-hero .stButton>button{background:#fff;color:var(--rzp-navy);border:0;width:100%;}
.st-key-hero .stButton>button:hover{background:#EAF3FF;color:var(--rzp-navy);}
/* pills */
.pill{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:600;
 white-space:nowrap;line-height:1.4;margin:0 4px 4px 0;}
.chip{display:inline-block;white-space:nowrap;border:1px solid var(--border);background:#fff;border-radius:999px;padding:3px 10px;font-size:12px;
 font-weight:500;color:var(--text);margin:0 6px 6px 0;}
.chip.blue{background:var(--rzp-blue-soft);border-color:#CFE3FF;color:var(--rzp-blue-dark);}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12.5px;}
/* buttons */
.stButton>button,.stFormSubmitButton>button{border-radius:10px;font-weight:600;border:1px solid var(--rzp-blue);
 background:#fff;color:var(--rzp-blue);transition:all 150ms ease;padding:.35rem .9rem;}
.stButton>button:hover,.stFormSubmitButton>button:hover{background:var(--rzp-blue-soft);color:var(--rzp-blue-dark);border-color:var(--rzp-blue-dark);}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:var(--rzp-blue);color:#fff;border-color:var(--rzp-blue);}
.stButton>button[kind="primary"]:hover,.stFormSubmitButton>button[kind="primary"]:hover{background:var(--rzp-blue-dark);color:#fff;}
[data-testid="stBaseLinkButton-secondary"]{background:#fff !important;color:var(--rzp-blue) !important;
 border:1px solid var(--rzp-blue) !important;border-radius:10px !important;font-weight:600;transition:all 150ms ease;}
[data-testid="stBaseLinkButton-secondary"]:hover{background:var(--rzp-blue-soft) !important;color:var(--rzp-blue-dark) !important;}
[data-testid="stBaseLinkButton-secondary"] p{font-weight:600;}
.st-key-card_public_flow{gap:14px;}
[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--rzp-blue) !important;color:#fff !important;border-color:var(--rzp-blue) !important;}
[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:var(--rzp-blue-dark) !important;}
.stButton>button:disabled,.stButton>button[disabled]{opacity:.45;cursor:not-allowed;}
/* queue rows */
.qgrid{display:grid;grid-template-columns:78px minmax(0,3fr) 112px minmax(0,1.15fr) 82px 118px 34px;gap:12px;align-items:center;}
.qgrid .pill{margin:0;}
[data-testid="stButtonGroup"],[data-testid="stButtonGroup"]>div{flex-wrap:wrap !important;overflow:visible !important;}
.qhead{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:0 15px;}
[class*="st-key-qrow"]{background:#fff;border:1px solid var(--border);border-radius:12px;padding:10px 14px;margin-bottom:-6px;
 transition:box-shadow 150ms ease,border-color 150ms ease;}
[class*="st-key-qrow"]:hover{border-color:#BFD8FF;box-shadow:var(--shadow-hover);}
[class*="st-key-qrow"] [data-testid="stHorizontalBlock"]{align-items:center;gap:10px;}
[class*="st-key-qrow"] p{margin:0;font-size:13px;}
.trunc{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;color:var(--text);font-size:13px;}
.sub{color:var(--muted);font-size:12px;}
/* chat */
.bubble{border-radius:14px;padding:14px 16px;font-size:14px;line-height:1.55;max-width:92%;}
.bubble.in{background:#F1F4F8;border-top-left-radius:4px;color:var(--text);}
.bubble.out{background:var(--rzp-blue-soft);border:1px solid #CFE3FF;border-top-right-radius:4px;margin-left:auto;color:var(--text);}
.bmeta{font-size:12px;color:var(--muted);margin:6px 2px 10px;}
.bmeta.r{text-align:right;}
.ailbl{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:700;color:var(--rzp-blue-dark);
 text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px;}
/* profile */
.kv{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px dashed var(--border);font-size:13px;}
.kv>span:first-child{color:var(--muted);white-space:nowrap;} .kv>span:last-child{font-weight:500;text-align:right;}
.evt .pill{white-space:normal;word-break:break-word;} .evt td{padding:6px 4px;vertical-align:middle;}
.rd{display:grid;grid-template-columns:64px 1fr;gap:10px;font-size:12.5px;padding:7px 0;border-bottom:1px solid var(--border);}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;}
.internal{font-size:10px;font-weight:700;color:var(--red);background:var(--red-soft);border-radius:6px;padding:1px 6px;margin-left:6px;}
.mini{font-size:12.5px;padding:6px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:8px;}
/* steps */
.steps{position:relative;margin-top:6px;}
.step{display:flex;gap:12px;position:relative;padding-bottom:14px;}
.step:not(:last-child)::before{content:"";position:absolute;left:11px;top:24px;bottom:0;width:2px;background:var(--border);}
.step .ic{width:24px;height:24px;border-radius:50%;flex:0 0 24px;display:flex;align-items:center;justify-content:center;
 font-size:12px;font-weight:700;color:#fff;z-index:1;}
.step .ic.ok{background:var(--green);} .step .ic.bad{background:var(--red);} .step .ic.na{background:#CBD5E1;}
.step .st{font-size:13px;font-weight:600;color:var(--text);} .step .sd{font-size:12px;color:var(--muted);}
.step.bad .sd{color:var(--red);}
.final{margin-top:4px;padding:12px;border-radius:10px;font-weight:600;font-size:13px;display:flex;justify-content:space-between;align-items:center;}
.lbl{font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);margin:14px 0 6px;}
.lbl:first-child{margin-top:0;}
/* alerts, empty */
.alert{display:flex;align-items:center;gap:14px;background:var(--red-soft);border:1px solid #F8C9CB;border-radius:14px;
 padding:14px 18px;color:#9F1F23;font-size:14px;}
.alert i{font-size:20px;color:var(--red);}
.empty{text-align:center;padding:28px 10px;color:var(--muted);font-size:13px;}
.empty i{font-size:28px;color:#9DB3D3;display:block;margin-bottom:8px;}
.hl{background:var(--red-soft);color:var(--red);font-weight:600;border-radius:4px;padding:0 3px;}
/* timeline */
.tl{border-left:2px solid #CFE3FF;padding-left:18px;margin-left:6px;}
.tl-item{position:relative;margin-bottom:16px;}
.tl-item::before{content:"";position:absolute;left:-25px;top:6px;width:12px;height:12px;border-radius:50%;background:var(--red);
 box-shadow:0 0 0 4px var(--red-soft);}
/* inputs */
.stTextInput input,.stTextArea textarea,[data-baseweb="select"]>div{border-radius:10px !important;}
[data-testid="stMetric"]{display:none;}
div[data-testid="stToast"]{border-radius:12px;}
</style>
"""


def inject():
    st.markdown(CSS.replace("__LOGO__", logo_data_uri()), unsafe_allow_html=True)


FLOWCHART_URL = "https://drive.google.com/file/d/14keOBeQdPOF8bvTfpUPuagpBz4nZKyXW/view?usp=sharing"


def flowchart_link(sub="How every ticket is handled · opens in a new tab"):
    return (f'<a class="flowlink" href="{FLOWCHART_URL}" target="_blank" rel="noopener noreferrer">'
            f'<i class="bi bi-diagram-3"></i><span>System flowchart ↗<small>{esc(sub)}</small></span></a>')


def topnav(on_home):
    """Top bar. The Razorpay logo is a real button that returns to the Overview page."""
    with st.container(key="topnav"):
        c = st.columns([1.05, 1.5, 4.2, 2.1], gap="small")
        c[0].button("Razorpay — back to Overview", key="logo_home", on_click=on_home)
        c[1].markdown('<div style="display:flex;align-items:center;gap:16px"><div class="div" '
                      'style="width:1px;height:26px;background:#E3E8F0"></div>'
                      '<div style="font-weight:600;font-size:15px;white-space:nowrap">Support Copilot</div></div>',
                      unsafe_allow_html=True)
        c[2].markdown('<div class="topnav-search" style="display:flex;align-items:center;gap:8px;background:#F2F5FA;'
                      'border:1px solid #E3E8F0;border-radius:10px;padding:7px 12px;color:#64748B;font-size:13px">'
                      '<i class="bi bi-search"></i> Search tickets, merchants, payment IDs…</div>', unsafe_allow_html=True)
        c[3].markdown(f'<div style="display:flex;justify-content:flex-end;align-items:center;gap:12px">'
                      f'{pill("Prototype · Synthetic data", label="Prototype · Synthetic data", kind="High")}'
                      f'<div class="avatar">PA</div></div>', unsafe_allow_html=True)


def section(title, subtitle=""):
    st.markdown(f'<div class="sh"><h3>{esc(title)}</h3>{f"<p>{esc(subtitle)}</p>" if subtitle else ""}</div>',
                unsafe_allow_html=True)


def gap():
    st.markdown('<div class="gap"></div>', unsafe_allow_html=True)


def empty(icon, text):
    return f'<div class="empty"><i class="bi bi-{icon}"></i>{esc(text)}</div>'


def kpi(icon, color, value, label, ctx=""):
    return f"""<div class="hcard kpi">
<div class="kpi-icon" style="background:{C[color + '_soft']};color:{C[color]}"><i class="bi bi-{icon}"></i></div>
<div class="kpi-value num">{value}</div><div class="kpi-label">{esc(label)}</div><div class="kpi-ctx">{ctx}</div></div>"""
