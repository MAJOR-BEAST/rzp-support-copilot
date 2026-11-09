# Merchant Support Copilot — Razorpay Campus AI Build-a-thon (Problem 1)

## What it does

- Reads 150 merchant support tickets (English and Hinglish) and decides a **category**, an **action** (Auto-resolve / Ask for info / Escalate), an **escalation team** and a **risk level** for each.
- Drafts a 40–90 word reply in the merchant's own language style, using that merchant's real system data and the knowledge base.
- Guardrails check every reply so it never invents a date, amount, refund, waiver, release or timeline. Threats, angry merchants, repeat contacts and claim-vs-system mismatches always go to a human.
- Flags platform-wide payment incidents and gaps in the knowledge base.
- Ships an agent console (Streamlit) with a queue, ticket detail, approve/edit/escalate buttons and a live "Try a ticket" mode.

## How to run

```bash
pip install pandas openpyxl anthropic pinecone streamlit numpy python-dotenv scikit-learn pytest tabulate
python run_pipeline.py && python -m copilot.evaluate
streamlit run app.py
```

Before the first run, create `.env` with `ANTHROPIC_API_KEY`, `PINECONE_API_KEY`, `MODEL_FAST=claude-haiku-5-5`,
`MODEL_DRAFT=claude-sonnet-5-5`, `VECTOR_BACKEND=pinecone` (or `local` for TF-IDF, which needs no Pinecone) and `APP_PASSWORD`.
Run tests with `python -m pytest -q`. `run_pipeline.py --no-draft` does triage only.

Outputs (in `outputs/`): `triage_results.xlsx` (sheets `results` and `summary`), `would_not_send.csv`, `incidents.csv`,
`kb_gaps.csv`, `metrics.md`, `mismatches.csv`, `manual_check_20.xlsx`.

## Architecture: 4 stages

```
1. INTAKE & SAFETY GATES   regex extract (merchant ID, payment ID, Rs amount, "N days")
                           → threat keywords (Legal / Compliance / Security)
                           → missing merchant ID? → classifier (Haiku): category, sub-intent, confidence, sentiment, language
                           → confidence < 0.80? → repeat contact (4th+ ticket) → claim-vs-system mismatch
2. POLICY ENGINE           deterministic rules (S1–S5, P1–P3, R0–R3, C1–C3, K1–K3, F1–F2, A1–A2, AC1–AC3, T, Q1–Q2)
                           → DecisionCard: action, team, risk, KB ids, allowed_facts, flags
                           → risk modifiers: angry +1, repeat +1 (both block auto-send)
3. DRAFT & GUARDRAILS      retrieve KB (Pinecone multilingual-e5-large, unioned with the rule's KB)
                           → draft (Sonnet) with {{placeholders}} that Python fills in
                           → promise firewall → specificity test → critic (Haiku) → send mode
4. BATCH                   incidents (payment failures, 24h window, ≥3 merchants), KB gaps, evaluation
```

Code: `copilot/` holds `extract`, `threats`, `classify`, `rules`, `vectorstore`, `draft`, `guardrails`, `batch`, `evaluate` and `llm` (the cache).
`run_pipeline.py` runs the batch end to end; `app.py` is the console.

## AI vs rules split

| AI (LLM) does | Deterministic code does |
|---|---|
| Classify intent, sub-intent, sentiment, language (Haiku) | Threat detection by keyword (the classifier can only add threats, never remove them) |
| Write the reply text in English or Hinglish (Sonnet) | Every action, team and risk decision (`rules.py`) |
| Second-opinion critic on tone and policy (Haiku) | Every merchant fact in a reply: the LLM writes `{{expected_settlement_date}}` and Python fills in the system value |
| | Business-day maths, repeat contact, mismatch detection, the promise firewall, send mode, incidents |

The LLM never decides policy and never types a merchant date or amount.

## Guardrails

1. **Promise firewall** (regex, deterministic). Every date and number in the final reply must appear in that ticket's `allowed_facts`
   or in the cited KB text. It blocks commitment phrases ("72 hours", "approved", "waive", "guarantee", "by tomorrow", "will be released",
   plus Hinglish forms such as "kal tak" and "release ho jayega"). It blocks any duration in an escalation reply, and any risk reason
   on hold, phishing and threat tickets. A failure gives `DO_NOT_SEND` and an entry in `would_not_send.csv`.
2. **Specificity test.** The reply must contain a merchant-specific value (merchant ID, system date or amount, payment ID).
   For an Ask, a question is enough. On failure the draft is regenerated once; if it fails again, the ticket goes to `HUMAN_WRITE`.
3. **Critic** (Haiku). It checks for admission of fault, blame, a leaked risk reason, wrong language, promises and whether the
   reply answers the question. A failure gives `HUMAN_REVIEW`.
4. **Send mode.** `AUTO_SEND` only when all of these hold: action Auto-resolve, confidence ≥ 0.80, not angry, not a repeat contact,
   no mismatch, and all three checks pass. Threats use a fixed acknowledgement template and are never auto-sent.
5. **Reproducibility.** Every LLM response is cached in `cache/llm/<sha256>.json` and retrieval results in `cache/retrieval/`.
   A second run makes 0 API calls. The pipeline never reads `data/answer_key.csv`; only `copilot/evaluate.py` does.

## Results (from `outputs/metrics.md`)

| Metric | Value |
|---|---|
| Category accuracy | 100.0% |
| Sub-intent accuracy | 99.3% |
| Action accuracy | **99.3%** |
| Team accuracy | **100.0%** |
| Risk accuracy | 98.7% |
| Send-mode accuracy | 99.3% |
| Critical errors (threat auto-sent, firewall bypass, escalation auto-sent, missed threat) | **0** |
| Auto-send share | 47.3% (71/150) |
| Accuracy within auto-sent tickets | 100.0% |
| Specificity pass rate | 100.0% |
| Fact coverage (must-mention dates, amounts, payment IDs) | 96.9% (31/32) |
| Would-not-send (firewall blocks in the final run) | 0 (4 blocked during development; covered by tests) |
| Incidents found | 4 (INC-001 to INC-004, 3–4 merchants each) |
| KB gaps | 1 cluster: `api_unknown`, 4 tickets (502s, rate limits, timeouts, blank popup) |

There are 3 tickets where the copilot disagrees with the answer key. For T-0013 and T-0067, vague tickets get a clarifying
question instead of an answer. For T-0053, the critic held a KYC reply for human review. All three disagreements are on the
cautious side.

## Assumptions and known limitations

- **30 Sep 2026 snapshot (J2).** Merchant data is used as "current" for every September ticket. For example, holds that started 26–28 Sep
  are applied to hold tickets dated earlier, and "last settlement 28 Sep" is quoted on a ticket dated 2 Sep.
- **Business days (J4)** exclude weekends only. Bank holidays are not in the data.
- **The answer key is ours, not Razorpay's.** `data/answer_key.csv` is hand-labelled message types plus the written KB policy rules,
  built independently of the AI classifier. It is not Razorpay's hidden answer set, so accuracy on unseen data may be lower.
- **Pinecone runs in AWS us-east-1**, which is acceptable for this synthetic data. In production, RBI data-localisation rules would
  require an India-hosted store (Qdrant or pgvector). That swap sits behind the `VectorStore` interface. `VECTOR_BACKEND=local` uses TF-IDF.
- **No temperature setting.** The current Claude API rejects `temperature` for `claude-haiku-5-5` and `claude-sonnet-5-5`, so it is not sent.
  Thinking is switched off (`disabled` on Haiku, `between_tools` on Sonnet). Determinism comes from the response cache.
- **The cache is not committed.** It is git-ignored, so a fresh clone makes the API calls once to rebuild it.
- **Technical errors** (502s, timeouts, rate limits, blank popup) are classed as `api_integration / api_unknown` (rule A2) rather than
  `payment_failure / tech_error_unknown` (P1). This matches the answer key. Both rules give Escalate, Tech Support, High, kb_gap.
- **A classifier `secondary_category: threat` is ignored.** Threats come only from keywords or a primary threat label; otherwise a pricing
  ultimatum ("reduce my rate or I'll move") would be treated as a legal threat.
- **Python 3.14** was used (3.11 is not installed on the build machine). The Streamlit app sets `runner.magicEnabled = false`
  because Streamlit "magic" mis-parses `if` blocks on 3.14.
- **Soft follow-up phrases** such as "hum trace karenge" can pass the critic. They are not dates or amounts, so the firewall allows them.

## Tools used

Python 3.14 · pandas · numpy · openpyxl · Anthropic Claude API (Haiku 5.5 classifier and critic, Sonnet 5.5 drafter) ·
Pinecone serverless with integrated `multilingual-e5-large` embeddings · scikit-learn (TF-IDF fallback) · Streamlit · pytest ·
python-dotenv · Claude Code (build assistant).
