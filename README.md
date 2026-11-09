# Merchant Support Copilot — Razorpay Campus AI Build-a-thon (Problem 1)

Triage copilot for 150 merchant support tickets. For each ticket it decides: category, action
(Auto-resolve / Ask for info / Escalate), escalation team, and risk level. It then drafts a reply in the
merchant's language (English or Hinglish) using the merchant's real data and the knowledge base. Guardrails
make sure no reply ever invents a date, amount, refund, waiver or release.

## Results (vs `data/answer_key.csv`)

| Metric | Value |
|---|---|
| Action accuracy | 99.3% |
| Team accuracy | 100% |
| Risk accuracy | 98.7% |
| Send-mode accuracy | 99.3% |
| Critical errors (threat/escalation auto-sent, firewall bypass, missed threat) | 0 |
| Auto-send share | 47% (71/150), 100% correct within auto-sent |

Full details are in `outputs/metrics.md`. The answer key is hand-labelled and follows the written KB policy;
it is not Razorpay's hidden answer set.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on macOS/Linux)
pip install pandas openpyxl anthropic pinecone streamlit numpy python-dotenv scikit-learn pytest tabulate
```

Create `.env` (never commit it):
```
ANTHROPIC_API_KEY=...
PINECONE_API_KEY=...
MODEL_FAST=claude-haiku-5-5
MODEL_DRAFT=claude-sonnet-5-5
VECTOR_BACKEND=pinecone        # or: local  (TF-IDF fallback, no Pinecone needed)
APP_PASSWORD=...
```

## Run

```bash
python run_pipeline.py              # full pipeline -> outputs/ (add --no-draft for triage only)
python -m copilot.evaluate          # metrics.md, mismatches.csv vs data/answer_key.csv
python -m pytest -q tests           # guardrail tests
streamlit run app.py                # agent console (reads outputs/ only; "Try a ticket" calls the API)
```

Outputs: `triage_results.xlsx` (sheets `results` and `summary`), `would_not_send.csv`, `incidents.csv`,
`kb_gaps.csv`, `metrics.md`, `mismatches.csv`, `manual_check_20.xlsx`.

## Design

```
ticket ─► extract (regex) ─► threat keywords ─► classify (Haiku, cached) ─► policy engine (deterministic rules)
                                                                              │ DecisionCard: action/team/risk,
                                                                              │ allowed_facts, KB ids, flags
        ┌─────────────────────────────────────────────────────────────────────┘
        ▼
retrieve KB (Pinecone multilingual-e5-large ∪ rule KB) ─► draft (Sonnet, {{placeholders}} filled in Python)
        ─► promise firewall (regex) ─► specificity test ─► critic (Haiku) ─► send mode
        ─► batch: incidents (24h, ≥3 merchants), KB gaps
```

- **The LLM never decides policy.** It only classifies intent and writes text. The action, team and risk
  come from `copilot/rules.py` (rules S1–S5, P1–P3, R0–R3, C1–C3, K1–K3, F1–F2, A1–A2, AC1–AC3, T, Q1–Q2).
- **Merchant facts are placeholders.** The drafter writes `{{expected_settlement_date}}` and similar;
  Python fills in the system value. The model never types a date or amount.
- **Promise firewall.** Every date and number in the final reply must appear in that ticket's
  `allowed_facts` or in the cited KB text. Commitment phrases are blocked ("72 hours", "approved", "waive",
  "guarantee", "will be released"…, plus Hinglish forms like "kal tak" and "release ho jayega"). Escalation
  replies cannot contain any duration. S5/C1/K2/threat replies cannot name a risk reason.
- **Send mode.** `AUTO_SEND` requires all of these: action Auto-resolve, confidence ≥ 0.80, not angry,
  not a repeat contact, no claim-vs-system mismatch, firewall pass, specificity pass and critic pass.
  Threats are never auto-sent. A firewall failure gives `DO_NOT_SEND`.
- **Threat replies** use a fixed acknowledgement template (English/Hinglish). The LLM writes none of it.
- **Reproducibility.** Every LLM response is cached at `cache/llm/<sha256(model+system+prompt)>.json`, and
  retrieval results at `cache/retrieval/`. A second run makes 0 API calls.
- **The pipeline never reads `data/answer_key.csv`.** Only `copilot/evaluate.py` does.

## Assumptions

- **J2 snapshot.** Merchant data is a 30 Sep 2026 snapshot, used as "current" for every September
  ticket. For example, holds that started 26–28 Sep are applied to hold tickets dated earlier, and
  "last settlement 28 Sep" is quoted on a ticket dated 2 Sep.
- **Business days (J4)** exclude weekends only. Bank holidays are not in the data.
- **Temperature.** The current Claude API rejects `temperature` for `claude-haiku-5-5` and
  `claude-sonnet-5-5` ("Extra inputs are not permitted"), so it is not sent. Thinking is switched off
  (`disabled` on Haiku, `between_tools` on Sonnet). Otherwise default thinking used up `max_tokens` and
  returned empty text. Determinism comes from the response cache.
- **Python 3.14** was used (3.11 is not installed on the build machine). No 3.12+-only syntax is
  used apart from `X | None` type hints, which work on 3.10+.
- **Technical errors** (502s, timeouts, rate limits, blank popup) are classified as `api_integration /
  api_unknown` (rule A2) rather than `payment_failure / tech_error_unknown` (P1). This matches the answer key.
  Both rules give the same result: Escalate, Tech Support, High, kb_gap.
- **Threats only come from keywords or a *primary* classifier label.** A classifier's
  `secondary_category: threat` is ignored. Otherwise a pricing ultimatum ("reduce my rate or I'll move")
  would be treated as a legal threat.
- **Vague tickets** ("Settlement issue M1019", "Payment failed. M1011") get one clarifying question (Q2)
  rather than an answer. This is the safer choice, and it accounts for the 2 action disagreements with the answer key.
- **The firewall does not allow merchant-typed numbers** (for example an error code "502") to be repeated
  back. The drafter is told not to echo them. When it did echo one during development, the draft was blocked.
- **The vector store** is Pinecone serverless in AWS us-east-1, which is acceptable for this synthetic data.
  In production, RBI data-localisation rules would call for an India-hosted store (Qdrant or pgvector). That
  is a drop-in swap behind the `VectorStore` interface in `copilot/vectorstore.py`. `VECTOR_BACKEND=local` uses TF-IDF
  and needs no external service.
- **The Streamlit app** runs with `runner.magicEnabled = false`. Streamlit "magic" mis-parsed `if` blocks
  on Python 3.14.

## Repo layout

```
copilot/  llm.py data_loader.py extract.py threats.py classify.py rules.py vectorstore.py
          draft.py guardrails.py batch.py evaluate.py
run_pipeline.py   app.py   tests/test_guardrails.py   .streamlit/config.toml
data/ (data pack, answer key)   docs/ (student brief)   outputs/
```
