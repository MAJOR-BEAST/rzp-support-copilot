"""Threat keyword detector (case-insensitive, Hinglish included). Order = precedence."""
import re

# (sub_intent, team, patterns)
THREAT_RULES = [
    ("threat_security", "Security", [
        r"data\s+leak", r"card\s+details\s+(were\s+)?visible", r"logged\s+into\s+my\s+dashboard",
        r"changed\s+my\s+bank\s+account", r"i\s+did\s+not\s+do\s+this", r"account\s+hack", r"hack(ed|ing)?\b",
    ]),
    ("threat_bribery", "Compliance", [
        r"\bcommission\b", r"\bbribe\b", r"\brishwat\b", r"asked\s+me\s+for\s+(a\s+)?(money|commission|payment|cash)",
    ]),
    ("threat_regulator", "Compliance", [r"\brbi\b", r"\bregulator\b", r"\bombudsman\b"]),
    ("threat_legal", "Legal", [
        r"legal\s+notice", r"\blawyer\b", r"\bcourt\b", r"consumer\s+forum", r"which\s+law",
        r"fraud\s+kar\s+rahe", r"you\s+are\s+doing\s+fraud", r"\bvakil\b",
    ]),
    ("threat_media", "Legal", [r"\btwitter\b", r"\blinkedin\b", r"\bpress\b", r"\bmedia\b", r"tagging\s+your\s+ceo"]),
    ("threat_legal", "Legal", [r"\bpolice\b"]),
]

SUBINTENT_TEAM = {
    "threat_legal": "Legal", "threat_regulator": "Compliance", "threat_security": "Security",
    "threat_media": "Legal", "threat_bribery": "Compliance",
}


def detect_threat(text: str):
    """Return (sub_intent, team, matched_keyword) or None."""
    t = text or ""
    for sub, team, pats in THREAT_RULES:
        for p in pats:
            m = re.search(p, t, re.I)
            if m:
                return sub, team, m.group(0)
    return None
