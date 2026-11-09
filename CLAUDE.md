# CLAUDE.md — Razorpay Merchant Support Copilot (Build-a-thon, Problem 1)

You are building a working prototype in ~50 minutes. Speed over polish. Every phase ends with a runnable checkpoint; never leave the repo broken. All logic below is FINAL (decided by the owner) — implement it exactly, do not redesign.

## 0. Goal and deliverables
For each of 150 merchant support tickets: (1) category, (2) action = Auto-resolve / Ask for info / Escalate, (3) escalation team, (4) risk level, (5) drafted reply in the merchant's language style (English or Hinglish) using the merchant's real data + knowledge base — with guardrails so no reply ever invents a date, refund, waiver or release.

Outputs (in `outputs/`):
1. `triage_results.xlsx` — all 150 rows (columns in §9).
2. `would_not_send.csv` — every blocked draft + reason.
3. `incidents.csv`, `kb_gaps.csv`.
4. `metrics.md` — evaluation results (§10).
5. Streamlit app `app.py` showing all of the above (agent console).

## 1. Stack
- Python 3.11, `pandas`, `openpyxl`, `anthropic`, `pinecone` (current SDK, package name `pinecone`), `streamlit`, `numpy`, `python-dotenv`, `scikit-learn` (fallback retrieval only).
- `.env`: `ANTHROPIC_API_KEY`, `PINECONE_API_KEY`, `MODEL_FAST=claude-haiku-5-5`, `MODEL_DRAFT=claude-sonnet-5-5`, `VECTOR_BACKEND=pinecone|local`.
- All LLM calls: temperature 0, JSON output, cached to `cache/llm/<sha256 of model+prompt>.json`. Re-runs must not call the API again (reproducibility is a disqualification criterion).
- Input: `data/Buildathon_Student_Data_Pack.xlsx` (tabs `P1_Tickets`, `P1_Merchants`, `P1_KnowledgeBase`). `data/answer_key.csv` (expected verdict for ALL 150 tickets — the accuracy benchmark). Optional: `data/P1_Gold_Labels_40.xlsx` (owner's hand labels).

## 2. Repo layout
```
copilot/
  data_loader.py     # load tabs, parse dates, merchant lookup dict
  extract.py         # regex extraction (§3 step 2)
  threats.py         # threat keyword detector (§3 step 3)
  classify.py        # LLM intent classifier (§4)
  rules.py           # deterministic policy engine (§5) -> DecisionCard
  vectorstore.py     # VectorStore interface: PineconeStore, LocalStore (TF-IDF)
  draft.py           # retrieval + LLM drafting with placeholders (§6)
  guardrails.py      # promise firewall, specificity test, critic (§7)
  batch.py           # incidents, KB gaps (§8)
  evaluate.py        # metrics vs gold labels (§10)
run_pipeline.py      # end-to-end over 150 tickets -> outputs/
app.py               # Streamlit console (§11)
tests/test_guardrails.py
README.md
```

## 3. Stage 1 — intake and safety gates (order matters)
1. Load the ticket.
2. **Extract (regex, no AI):** `merchant_id` = ticket column, else regex `M\d{4}` in text; `payment_id` = `pay_[A-Za-z0-9]+`; `amount_inr` = `Rs\.?\s?[\d,]+` → int; `days_ago` = `(\d+)\s*(din|days?)`; `created_at` parsed as datetime.
3. **Threat check** (keyword regex, case-insensitive, Hinglish included) OR classifier `category == "threat"`. If threat → Decision: action Escalate, risk Critical, team by sub-type, reply = acknowledgement template only (§6.4). Skip to Stage 3. Keyword → team map:
   - legal notice, lawyer, court, consumer forum, consumer court, "which law", "fraud kar rahe", "you are doing fraud" → **Legal**
   - RBI, regulator, ombudsman → **Compliance**
   - commission / bribe / "asked me for" money by employee → **Compliance**
   - data leak, card details visible, "logged into my dashboard", "changed my bank account", "I did not do this" → **Security**
   - Twitter, LinkedIn, press, media, "tagging your CEO" → **Legal**
   - police → **Legal**
4. **Merchant ID present?** No → action Ask, risk Low, category = classifier's best guess (or Unclear), reply asks for merchant ID (and payment ID if refund/specific payment). No merchant lookup.
5. **Classify** (LLM, §4) → category, sub_intent, confidence, sentiment, language.
6. **Confidence ≥ 0.80?** No → action Ask, risk Medium, one targeted question that mentions the merchant's current status (e.g. payouts on hold).
7. **Fetch context:** merchant row; `repeat_contact` = this ticket is the merchant's 4th or later ticket by created_at (count only earlier + current tickets — no future leakage).
8. **Claim vs system mismatch** (deterministic): settlement complaint but `settlement_status == "Settled"` → `mismatch="claims not received; system shows Settled"` (still handled by rule S2, but mismatch blocks auto-send); dispute-debit complaint but `open_chargebacks == 0` → mismatch (rule C1).
9. **Multi-intent:** classifier returns `secondary_category`; the higher-risk category decides (risk order: threat > account_closure > settlement hold > refund ≥1L > payment_failure > others).

## 4. Classifier (MODEL_FAST, JSON only)
Categories: `settlement, payment_failure, refund, chargeback, kyc, fees_pricing, api_integration, account_change, threat, unclear`.
Sub-intents (must be one of):
- settlement: `settlement_status`
- payment_failure: `payment_failure_general`, `tech_error_unknown` (502, timeouts, rate-limit, blank popup, errors with no KB article)
- refund: `refund_status`
- chargeback: `chargeback_what_to_do`, `chargeback_block_request`, `chargeback_debit_no_notice`
- kyc: `kyc_documents`, `kyc_reverify_genuine`
- fees_pricing: `fees_invoice`, `fees_negotiation` (waiver, MDR dispute, rate cut, competitor threat)
- api_integration: `api_signature`, `api_amount_mismatch`, `api_auth_failed`, `api_webhook`, `api_unknown`
- account_change: `account_contact_change`, `account_entity_change`, `account_closure`
- threat: `threat_legal`, `threat_regulator`, `threat_security`, `threat_media`, `threat_bribery`
- unclear: `unclear`
Return: `{category, sub_intent, secondary_category|null, confidence 0-1, sentiment: calm|frustrated|angry, language: English|Hinglish, summary_one_line, reasoning_short}`.
Prompt must include 1-line definitions of every sub-intent and 6 few-shot examples covering Hinglish and threats. Hinglish = Hindi in Latin script.

## 5. Stage 2 — policy engine (deterministic, `rules.py`)
Output a `DecisionCard`: `category, sub_intent, action, team, risk (Low/Medium/High/Critical), rule_id, kb_ids, allowed_facts (dict), flags (list), reason_plain`.
`allowed_facts` = ONLY values the reply may contain (merchant fields + KB policy numbers for the cited KB articles).

| rule_id | Condition | Action | Team | Risk | KB | Allowed facts / reply content |
|---|---|---|---|---|---|---|
| S1 | settlement, status Delayed | Auto | — | Low | KB-01, KB-02 | expected_settlement_date (system only) |
| S2 | settlement, status Settled | Auto | — | Low | KB-01 | last_settlement_date, last_settlement_amount_inr; ask for UTR if still not visible; WARM tone (owner decision J1) |
| S3 | settlement, On hold, KYC pending | Auto | — | Medium | KB-04 | Dashboard > Account > KYC; released within 1 business day after verification |
| S4 | settlement, On hold, Bank account mismatch | Auto | — | Medium | KB-05 | Dashboard > Settings > Bank Account; penny-drop within 24 hours |
| S5 | settlement, On hold, Risk review OR Chargeback reserve | Escalate | Risk Ops | High | KB-03 | NO reason, NO timeline (owner decision J3). Text: "escalated to the team that reviews holds; they'll update you directly on this ticket" |
| P1 | payment_failure, sub_intent tech_error_unknown | Escalate | Tech Support | High | none | flag `kb_gap` |
| P2 | payment_failure, payment_success_rate_7d_pct < 85 | Escalate | Payments Ops | High | KB-06 | never blame customers; may cite their success rate |
| P3 | payment_failure, success rate ≥ 85 | Auto | — | Low | KB-06 | retry/other method; deducted-but-failed auto-reverses in 5–7 business days |
| R0 | refund, no payment_id | Ask | — | Low | KB-16 | ask payment ID |
| R1 | refund, amount ≥ 100000 | Escalate | Refund Ops | High | KB-07 | no timeline |
| R2 | refund, business_days_elapsed ≤ 7 | Auto | — | Low | KB-07 | 5–7 business days; ARN available after 3 days |
| R3 | refund, business_days_elapsed > 7 | Escalate | Refund Ops | Medium | KB-07 | owner decision J5 |
| C1 | chargeback_debit_no_notice AND open_chargebacks == 0 | Escalate | Risk Ops | High | KB-08 | mismatch flag |
| C2 | chargeback_block_request | Auto | — | Medium | KB-08 | disputes cannot be blocked in advance; keep evidence ready |
| C3 | other chargeback | Auto | — | Medium | KB-08 | Dashboard > Disputes; evidence within 7 calendar days or lost. Never state a deadline DATE |
| K1 | kyc_reverify_genuine AND kyc_status == "Re-verification needed" | Auto | — | Medium | KB-10 | genuine only via Dashboard / @example.com emails |
| K2 | kyc_reverify_genuine AND kyc_status != "Re-verification needed" | Escalate | Security | High | KB-10 | likely phishing; do not share OTP/docs |
| K3 | kyc_documents | Auto | — | Low | KB-10 | document list |
| F1 | fees_negotiation | Escalate | Account Manager | Medium | KB-09 | no promise; flag `churn_risk` |
| F2 | fees_invoice | Auto | — | Low | KB-09 | invoices by 5th, Dashboard > Reports > Invoices |
| A1 | api_signature / api_amount_mismatch / api_auth_failed / api_webhook | Auto | — | Low | KB-12/13/14 | exact fix steps |
| A2 | api_unknown | Escalate | Tech Support | High | none | flag `kb_gap` |
| AC1 | account_contact_change | Auto | — | Low | KB-11 | Settings with OTP |
| AC2 | account_entity_change | Auto | — | Low | KB-11 | needs fresh application |
| AC3 | account_closure | Escalate | Account Manager + Risk Ops | Medium | KB-17 | after settlements/refunds/disputes cleared |
| T* | threat (any) | Escalate | per §3.3 | Critical | KB-15 | ack-only |
| Q1 | no merchant ID | Ask | — | Low | KB-16 | ask merchant ID (+ payment ID if refund) |
| Q2 | confidence < 0.80 or unclear | Ask | — | Medium | KB-16 | one targeted question using merchant status |

**Business days (owner decision J4):** `start = created_at.date() - days_ago calendar days`; `business_days_elapsed = numpy.busday_count(start, created_at.date())` (weekends excluded; bank holidays not in data → stated assumption). If `days_ago` missing → R2 wording without computing elapsed time.

**Risk modifiers (after rule):** sentiment angry → risk +1 level (cap Critical) and `block_auto`; repeat_contact → risk +1 and `block_auto`; mismatch → `block_auto`; urgency words ("today", "urgent", "abhi") → never add dates. Keep `action` unchanged by modifiers (action = what the case needs; send mode is separate).

**Assumption (owner decision J2):** merchant data is a 30 Sep 2026 snapshot used as "current" for all September tickets. Known limitation: e.g. holds started 26–28 Sep but tickets about holds are dated earlier. Report this in metrics.md.

## 6. Stage 3 — drafting
1. **Retrieve** (`vectorstore.py`): Pinecone index `rzp-kb` created with integrated embedding model `multilingual-e5-large` (`create_index_for_model`, AWS us-east-1, field_map text→`chunk_text`). Upsert 17 KB articles (id = kb_id, metadata topic). Second namespace `tickets` with all 150 ticket texts (metadata merchant_id, created_at, category) for similar-ticket retrieval and incidents. Query top-3 KB with the ticket text; ALWAYS union with the rule's `kb_ids` (rules win). `LocalStore` = TF-IDF cosine fallback with same interface (`VECTOR_BACKEND=local`). Record `retrieval_score`.
2. **Draft** (MODEL_DRAFT, JSON `{reply}`): system prompt contains: decision card, allowed_facts as `{{placeholder}}` keys, cited KB text, merchant's language (reply in same style: Hinglish → Hinglish in Latin script), sentiment-based tone (angry → acknowledge frustration first, calm and brief), and rules: use ONLY placeholders for any date/amount/percentage/duration from merchant data; never promise refund, waiver, release, date or timeline not in allowed_facts; never reveal risk reasons; never blame the customer; for Escalate say which team has it, no timeline; for Ask ask exactly what is missing; 40–90 words; sign off "— Razorpay Support". Then fill placeholders in Python.
3. **Ack templates** for threats (no LLM content beyond language choice): English: "Thank you for writing to us. We take this seriously and have escalated it to our {{team}} team, who will contact you directly. — Razorpay Support". Hinglish equivalent.

## 7. Guardrails (`guardrails.py`)
1. **Promise firewall** (deterministic): extract every number/date/₹ amount/percentage/duration from the final reply (normalise "Rs 12,000"/"₹12,000"/"12000"). Each must be in `allowed_facts` values or in the cited KB articles' text. Also regex-block commitment phrases unless the rule allows: `will (be )?(released|refunded|credited|waived)`, `guarantee`, `by tomorrow`, `today itself`, `within \d+ hours` (unless KB-05's 24h for S4), `waive`, `approved`, `refund the difference`, `we will release`, `72 hours`. Fail → status `BLOCKED`, add to `would_not_send.csv` with exact offending token.
2. **Specificity test:** pass if reply contains ≥1 merchant-specific value (any allowed_facts value from the merchant row, or the payment ID) OR (action Ask AND contains "?") OR rule is T*. Fail → regenerate once with feedback; still fail → `HUMAN_WRITE`.
3. **Critic** (MODEL_FAST, JSON `{pass: bool, issues: []}`) checklist: no admission of fault on threats; no blaming customer; no internal risk reason; language matches; no promise; answers the actual question. Fail → `HUMAN_REVIEW` with issues.
4. **Send mode:** `AUTO_SEND` only if action Auto AND confidence ≥ 0.80 AND not angry (owner decision J8: angry always human) AND not repeat_contact AND no mismatch AND firewall pass AND specificity pass AND critic pass AND category toggle ON (config dict, all ON by default). Else `HUMAN_REVIEW`; firewall fail → `DO_NOT_SEND`.

## 8. Stage 4 — batch (`batch.py`)
- **Incidents (owner decision J7):** payment_failure tickets; sliding 24h window; ≥3 distinct merchants → incident id, list of tickets/merchants, window. Flag only (`incident_id` column) — does NOT change per-ticket action. Write `incidents.csv`.
- **KB gaps:** tickets with flag `kb_gap` or max retrieval_score below 0.35 → group by sub_intent → suggested article title. Write `kb_gaps.csv`.

## 9. Output columns (`triage_results.xlsx`, sheet `results`)
`ticket_id, created_at, channel, merchant_id, merchant_message, language, sentiment, category, sub_intent, confidence, action, escalation_team, risk, rule_id, reason_plain, kb_cited, drafted_reply, send_mode, firewall_status, firewall_issue, specificity_pass, critic_issues, repeat_contact, mismatch, incident_id, flags`
Second sheet `summary`: counts by category, action, team, risk, send_mode.

## 10. Evaluation (`evaluate.py` → `metrics.md`)
- **Primary benchmark: `data/answer_key.csv`** (150 rows; columns `expected_category, expected_sub_intent, expected_action, expected_team, expected_risk, expected_send_mode, rule_id, must_mention, must_not_say`). The pipeline must NEVER read this file — only `evaluate.py` does. Compare per ticket: category, sub_intent, action, team, risk, send_mode → accuracy % each, confusion matrix for action, and a `outputs/mismatches.csv` listing every disagreement (ticket, expected vs got, rule fired, reply). Also check each drafted reply contains the `must_mention` facts (simple substring/fuzzy check on dates/amounts) → "fact coverage %". Headline numbers in metrics.md: action accuracy, team accuracy, critical errors, auto-send share and accuracy within auto-sent tickets.
- State in metrics.md: answer key = hand-labelled message types + written policy rules from the KB, built independently of the agent's AI classifier; it is NOT Razorpay's hidden answer set.
- If `data/P1_Gold_Labels_40.xlsx` has filled `my_category/my_action/my_escalation_team/my_risk`: category accuracy, action accuracy, team accuracy, risk accuracy, confusion matrix (action), list every mismatch with both labels. Map gold category names: Settlement→settlement, Payment failure→payment_failure, Refund→refund, Chargeback→chargeback, KYC→kyc, Fees & pricing→fees_pricing, API/Integration→api_integration, Account change/closure→account_change, Legal/Security threat→threat, Unclear→unclear.
- Always: critical-error count (firewall blocks reaching AUTO_SEND must be 0; threats with send_mode AUTO_SEND must be 0), auto-send share and its breakdown, specificity pass rate, would-not-send count with reasons, incidents found, KB gaps.
- If no gold labels: write a 20-ticket stratified sample to `outputs/manual_check_20.xlsx` for the owner to grade, and say so in metrics.md. Never claim accuracy without labels.

## 11. Streamlit app (`app.py`) — Giva-style agent console
- Loads `outputs/` files only (no API cost) by default.
- Sidebar: filters (category, action, team, risk, send_mode), per-category auto-send toggles (display only), counts.
- Main tab "Queue": table; select a ticket → panel: message, merchant facts, **Summary** (summary_one_line), sentiment badge, **Next step** (action + team + reason_plain), drafted reply, KB cited, firewall/critic status, flags. Buttons: Approve / Edit (text area) / Escalate (session state only).
- Tabs: "Would not send", "Incidents", "KB gaps", "Metrics" (render metrics.md), "Try a ticket" (text + merchant ID → runs full pipeline live with API; behind a password from `st.secrets`/env `APP_PASSWORD`).

## 12. Tests (`tests/test_guardrails.py`, pytest)
Firewall blocks: "will be released within 72 hours", "refund of Rs 50,000 approved", an invented date "05 Oct 2026" not in facts. Allows: S1 reply with the system's expected date. Threat ticket never AUTO_SEND. Business-days: ticket created Mon 21 Sep 2026 with "7 days" → start Mon 14 Sep → 5 business days (assert). Repeat-contact counts only earlier tickets.

## 14. Look and feel — Razorpay-style theme (Streamlit)
- `.streamlit/config.toml`:
```
[theme]
primaryColor = "#3395FF"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F3F6FB"
textColor = "#072654"
font = "sans serif"
```
- Inject CSS once in `app.py` via `st.markdown(<style>, unsafe_allow_html=True)`: Google Font `Inter` (weights 400/600/700) for all text; top header bar full-width navy `#072654`, white text "Merchant Support Copilot", small subtitle "Prototype · Razorpay Campus AI Build-a-thon"; page background `#F3F6FB`; content in white cards (border `1px solid #E3E8F0`, radius 10px, padding 16px, soft shadow); primary buttons `#3395FF` with white text, hover `#1F7AE0`; sidebar background `#072654` with white text and blue accent for selected items.
- KPI row at top of Queue tab: 4 metric cards (Total tickets · Auto-send % · Escalated · Accuracy vs answer key).
- Status pills (rounded, small caps): Auto-resolve green `#0E9F6E` on `#E7F7F1`; Ask purple `#6B4EFF` on `#EFEBFF`; Escalate red `#E5484D` on `#FDECEC`; risk Critical/High/Medium/Low = red/orange `#F59E0B`/blue `#3395FF`/grey `#64748B`.
- Do NOT use Razorpay's logo or wordmark image; text title only. Clean fintech dashboard look: lots of white space, no emojis in headers.

## 13. Build order (checkpoints — commit after each)
1. **(≤15 min)** loader, extract, threats, classify (cached), rules → `run_pipeline.py --no-draft` writes triage_results.xlsx with category/action/team/risk. ✅ submittable.
2. **(≤15 min)** vectorstore (Pinecone, local fallback), draft, guardrails → drafted replies, would_not_send.csv.
3. **(≤8 min)** batch + evaluate (vs `data/answer_key.csv`) → incidents, kb_gaps, mismatches.csv, metrics.md.
4. **(≤10 min)** app.py with the §14 theme; `streamlit run app.py` works locally.
5. README: setup, `python run_pipeline.py`, `streamlit run app.py`, design summary, assumptions (J2 snapshot, business days without holidays, Pinecone us-east-1 for synthetic data → production would use India-hosted Qdrant/pgvector for RBI data localisation, swap via VectorStore).
If a phase overruns, skip to the next checkpoint with what works; never block on Pinecone — use `VECTOR_BACKEND=local`.
