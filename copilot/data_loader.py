"""Load the P1 tabs. NEVER reads data/answer_key.csv."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "data" / "Buildathon_Student_Data_Pack.xlsx"
DATE_FMT = "%d %b %Y"


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    return v


def load_tickets() -> pd.DataFrame:
    df = pd.read_excel(XLSX, sheet_name="P1_Tickets")
    df["created_at"] = pd.to_datetime(df["created_at"], format="%d %b %Y %H:%M")
    df["merchant_id"] = df["merchant_id"].where(df["merchant_id"].notna(), None)
    return df.sort_values(["created_at", "ticket_id"]).reset_index(drop=True)


def load_merchants() -> dict:
    df = pd.read_excel(XLSX, sheet_name="P1_Merchants")
    return {r["merchant_id"]: {k: _clean(v) for k, v in r.items()} for _, r in df.iterrows()}


def load_kb() -> dict:
    df = pd.read_excel(XLSX, sheet_name="P1_KnowledgeBase")
    return {r["kb_id"]: {"kb_id": r["kb_id"], "topic": r["topic"], "guidance": r["guidance"]} for _, r in df.iterrows()}
