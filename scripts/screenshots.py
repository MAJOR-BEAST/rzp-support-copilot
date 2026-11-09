"""Playwright screenshots of every console page at 1440x900 -> screenshots/.

Usage: python scripts/screenshots.py [base_url] [width]
"""
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8502"
WIDTH = int(sys.argv[2]) if len(sys.argv) > 2 else 1440
OUT = ROOT / "screenshots" / ("" if WIDTH == 1440 else f"w{WIDTH}")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [("01_overview", "Overview", None), ("02_queue", "Ticket Queue", None),
         ("03_copilot_hold", "Copilot View", "T-0016"), ("04_copilot_threat", "Copilot View", "T-0027"),
         ("05_guardrails", "Guardrails", None), ("06_insights", "Insights", None),
         ("07_evaluation", "Evaluation", None), ("08_try", "Try a Ticket", None),
         ("09_flowchart_locked", "Flowchart", None), ("10_flowchart", "Flowchart", None)]


def settle(page, extra=3.0):
    page.wait_for_selector(".st-key-topnav", timeout=60000)
    for _ in range(60):
        if not page.query_selector('[data-testid="stStatusWidget"] [data-testid="stStatusWidgetRunningIcon"], .stSpinner'):
            break
        time.sleep(0.5)
    time.sleep(extra)


def full_height(page):
    return page.evaluate("""() => {
        const m = document.querySelector('[data-testid="stMain"]') || document.querySelector('section.main');
        const b = m ? m.querySelector('.block-container') : null;
        return Math.ceil((b ? b.scrollHeight : document.body.scrollHeight) + 60);
    }""")


def main():
    report = []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for name, pg, tid in PAGES:
            ctx = br.new_context(viewport={"width": WIDTH, "height": 900}, device_scale_factor=1)
            page = ctx.new_page()
            url = f"{BASE}/?page={quote(pg)}" + (f"&tid={tid}" if tid else "")
            page.goto(url)
            settle(page)
            if name == "10_flowchart" and page.get_by_role("button", name="Unlock flowchart").count():
                page.get_by_placeholder("Password").fill(os.getenv("APP_PASSWORD", ""))
                page.get_by_role("button", name="Unlock flowchart").click()
                settle(page, 6)
            if name == "08_try" and os.getenv("ANTHROPIC_API_KEY"):
                pw = page.query_selector('input[type="password"]')
                if pw:
                    pw.fill(os.getenv("APP_PASSWORD", ""))
                page.get_by_role("button", name="Run copilot").click()
                time.sleep(2)
                settle(page, 4)
            page.screenshot(path=str(OUT / f"{name}.png"))
            h = full_height(page)
            page.set_viewport_size({"width": WIDTH, "height": max(900, h)})
            time.sleep(1.5)
            page.screenshot(path=str(OUT / f"{name}_full.png"))
            errs = page.query_selector_all('[data-testid="stException"]')
            hscroll = page.evaluate("""() => {const m=document.querySelector('[data-testid="stMain"]');
                return m ? m.scrollWidth - m.clientWidth : 0}""")
            report.append((name, len(errs), hscroll, h))
            if errs:
                print(name, "EXCEPTION:", errs[0].inner_text()[:600])
            ctx.close()
        # navigation regression: queue "View" -> Copilot View, then "Next ticket" must stay there
        ctx = br.new_context(viewport={"width": WIDTH, "height": 900})
        page = ctx.new_page()
        page.goto(f"{BASE}/?page={quote('Ticket Queue')}")
        settle(page)
        page.get_by_role("button", name="View").nth(2).click()
        time.sleep(1); settle(page, 2)
        on_cv = page.get_by_text("Why this decision").count() > 0
        page.get_by_role("button", name="Next ticket →").click()
        time.sleep(1); settle(page, 2)
        still = page.get_by_text("Why this decision").count() > 0
        sel = page.evaluate("() => document.querySelector('[data-testid=\"stSelectbox\"]')?.innerText || ''")
        print(f"nav check: View->CopilotView={on_cv} NextTicket stays={still} selected={sel.strip()[:20]!r}")
        ctx.close()
        br.close()
    for r in report:
        print(f"{r[0]:22s} exceptions={r[1]} h_overflow_px={r[2]} content_h={r[3]}")


if __name__ == "__main__":
    main()
