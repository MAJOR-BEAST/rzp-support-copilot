# Metrics — Merchant Support Copilot

## Headline

| Metric | Value |
|---|---|
| Tickets | 150 |
| Action accuracy | **99.3%** |
| Team accuracy | **100.0%** |
| Critical errors | **0** |
| Auto-send share | 47.3% (71/150) |
| Accuracy within auto-sent | 100.0% |

## Benchmark

Benchmark = `data/answer_key.csv`: hand-labelled message types + the written policy rules from the KB, built independently of the agent's AI classifier. It is **NOT** Razorpay's hidden answer set. The pipeline never reads this file; only `copilot/evaluate.py` does.

| Field | Accuracy |
|---|---|
| category | 100.0% |
| sub_intent | 99.3% |
| action | 99.3% |
| escalation_team | 100.0% |
| risk | 98.7% |
| send_mode | 99.3% |
| rule_id | 98.7% |

**Fact coverage** (reply contains the must_mention dates / amounts / payment IDs): 96.9% (31/32 tickets with checkable facts)

Missing facts:

- T-0013: missing ['28 Sep 2026', 'Rs 55,000']

## Action confusion matrix (rows = expected, cols = got)

| expected     |   Ask for info |   Auto-resolve |   Escalate |
|:-------------|---------------:|---------------:|-----------:|
| Ask for info |              9 |              0 |          0 |
| Auto-resolve |              1 |             95 |          0 |
| Escalate     |              0 |              0 |         45 |

## Critical errors (must all be 0)

- Firewall-blocked drafts reaching AUTO_SEND: 0
- Threat tickets with AUTO_SEND: 0
- Expected-Escalate tickets auto-sent: 0
- Threat tickets not detected as threats: 0

## Send mode

| send_mode    |   count |
|:-------------|--------:|
| HUMAN_REVIEW |      79 |
| AUTO_SEND    |      71 |

Auto-send by category:

| category        |   auto_sent |
|:----------------|------------:|
| settlement      |          13 |
| refund          |          12 |
| payment_failure |          11 |
| fees_pricing    |           8 |
| chargeback      |           8 |
| account_change  |           7 |
| api_integration |           7 |
| kyc             |           5 |

Specificity pass rate: 100.0%

## Would-not-send (promise firewall blocks)

Count: 0

No final draft tripped the firewall in this run. The firewall is exercised by `tests/test_guardrails.py` (72 hours, 'refund of Rs 50,000 approved', invented date) and blocked 4 drafts during development (escalation drafts that added a '5-7 business days' timeline, and an echoed '502' error code), which led to tighter drafting rules.

## Incidents (J7: payment_failure, 24h sliding window, >=3 merchants)

| incident_id   | window_start        | window_end          |   n_tickets |   n_merchants | tickets                        | merchants                  | note                                                                                 |
|:--------------|:--------------------|:--------------------|------------:|--------------:|:-------------------------------|:---------------------------|:-------------------------------------------------------------------------------------|
| INC-001       | 2026-09-02 15:02:00 | 2026-09-02 21:06:00 |           3 |             3 | T-0009, T-0012, T-0014         | M1018, M1052, M1058        | Possible platform-wide payment degradation; flag only, per-ticket actions unchanged. |
| INC-002       | 2026-09-13 08:56:00 | 2026-09-13 20:44:00 |           3 |             3 | T-0067, T-0069, T-0074         | M1007, M1011, M1019        | Possible platform-wide payment degradation; flag only, per-ticket actions unchanged. |
| INC-003       | 2026-09-15 08:19:00 | 2026-09-15 18:50:00 |           4 |             4 | T-0080, T-0081, T-0082, T-0084 | M1013, M1017, M1027, M1033 | Possible platform-wide payment degradation; flag only, per-ticket actions unchanged. |
| INC-004       | 2026-09-20 20:57:00 | 2026-09-21 19:23:00 |           3 |             3 | T-0103, T-0105, T-0109         | M1008, M1052, M1053        | Possible platform-wide payment degradation; flag only, per-ticket actions unchanged. |

## KB gaps

| sub_intent   |   n_tickets | tickets                        |   max_retrieval_score | suggested_article_title                                                                    |
|:-------------|------------:|:-------------------------------|----------------------:|:-------------------------------------------------------------------------------------------|
| api_unknown  |           4 | T-0008, T-0047, T-0118, T-0145 |                 0.842 | Troubleshooting intermittent API errors (5xx, timeouts, rate limits, blank checkout popup) |

## Disagreements with the answer key

| ticket_id   | field      | expected               | got                     | rule_fired   | expected_rule   |
|:------------|:-----------|:-----------------------|:------------------------|:-------------|:----------------|
| T-0013      | action     | Auto-resolve           | Ask for info            | Q2           | S2              |
| T-0013      | risk       | Low                    | Medium                  | Q2           | S2              |
| T-0053      | send_mode  | AUTO_SEND              | HUMAN_REVIEW            | K3           | K3              |
| T-0067      | sub_intent | payment_failure_single | payment_failure_general | Q2           | R0/KB-16        |
| T-0067      | risk       | Low                    | Medium                  | Q2           | R0/KB-16        |

Full list incl. replies: `outputs/mismatches.csv`.

## Known limitations / assumptions

- **J2 snapshot:** merchant data is a 30 Sep 2026 snapshot used as 'current' for all September tickets. E.g. holds that started 26-28 Sep are applied to hold tickets dated earlier in September, and 'last settlement 28 Sep' is quoted on tickets dated 2 Sep.
- **Business days (J4)** exclude weekends only; bank holidays are not in the data.
- **Temperature:** the current Claude API rejects the `temperature` parameter for these models, and thinking is switched off. Reproducibility comes from the response cache (`cache/llm/`): a second run makes 0 API calls.
- Vague tickets (e.g. 'Settlement issue M1019', 'Payment failed. M1011') get a clarifying question (Q2) instead of an answer — the safer side of the trade-off.

## Owner gold labels

`data/P1_Gold_Labels_40.xlsx` not provided. A 20-ticket stratified sample is in `outputs/manual_check_20.xlsx` for the owner to grade.
