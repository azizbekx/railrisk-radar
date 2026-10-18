# Chat eval results (2026-10-18)

`python -m evals.chat_evals`, 10 cases, temperature 0.2, cases run 4 at a time. Latency is wall-clock per question
(all LLM round trips plus tools). "Before" = `buyer-workflow` code, rescored with the final checks.
"After" = this branch. To save credits, non-default models only re-ran the cases they had failed.

| Model | Before | After | Median / max latency (after) | Jury Q1 | Jury Q2 |
|---|---|---|---|---|---|
| **Nemotron-3-Ultra-550b-a55b** (default) | 8/10 | **10/10** (full re-run) | 6.5 s / 12.5 s | 4/4 | 4/4 (0/1 before) |
| Nemotron-3.5-Super-VL | 10/10 | jury only: 4/4 | 4.8 s / 7.9 s (before) | 3/3 | 3/3 |
| nemotron-3-super-120b-a12b | 9/10 | 10/10 (1 failure re-run) | 2.8 s / 8.3 s (before) | 1/1 after (0/1 before) | 1/1 |
| Nemotron-3_5-Lightning | 9/10 | 10/10 (1 failure re-run) | 2.5 s / 5.5 s (before) | 1/1 | 1/1 |
| NVIDIA-Nemotron-3-Nano-30B-A3B | 8/10 | 9/10 (2 failures re-run) | 9.9 s / 26.6 s (before), ~45 s on retries | 1/1 | 1/1 |

## Failures found and how they were fixed

| Model | Case | Failure | Fix |
|---|---|---|---|
| Ultra | jury_q2_tri_why | Wrote the full explanation next to the `show_chart` call, then ended with only "The chart above visualizes...". The UI showed the one-liner. | `run()` keeps an answer-like draft written next to side-effect tools (show_chart, add_to_shortlist) and merges it when the final message is short. The prompt now says the last message must hold the full answer. |
| Ultra | preset_compare_shortlist | `compare_suppliers(columns=["Compliance_Risk_Level", ...])` crashed (`int('High')`). The model retried, then made up a table with duplicated, mislabelled suppliers. | `*_Level` columns map to their score, and levels are returned next to the values. |
| Nano | preset_shortlist5 / compare_20 | Empty content (no tool call, no text), so the user got "(no answer)". | An empty reply before any tool use gets one retry with tools on. An empty reply after tool use gets one tool-free final-answer call. |
| Nano | compare_20 | Wrong "safest" supplier: get_suppliers for 20 IDs is about 34k chars, and the old blind `[:12000]` slice dropped rows (and broke the JSON). | `_fit()` sends compact JSON with a 40k budget. If a result is still too big, it drops level columns, then whole rows, with a `truncated` note, so the JSON stays valid. |
| Lightning | country_not_in_data | Made up "SUPP_00042 is in Germany". | DATA_SYSTEM now says plainly that the data has no country, location, category or identity, and never to name one. |
| Super-120b | jury_q1_financial | Correct ID, but did not mention SUPP_00731's Critical credit rating (76). | DATA_SYSTEM: always state the chosen supplier's Credit_Rating_Score and level. |
| Nano | preset_shortlist5 | Still fails: two empty replies, then it makes up a tool call in prose. | Not fixed. Nano is not recommended for the demo. |

Other hardening, covered offline by `evals/test_agent_offline.py`:
- Tool calls written as text (`<tool_call>{json}</tool_call>`, `<TOOLCALL>[..]</TOOLCALL>`, the XML
  `<function=..><parameter=..>` form, or bare/fenced `{"name", "arguments"}`) are turned into structured calls.
- Tool arguments are coerced to the schema: JSON-string or comma-separated lists, `supplier` vs `suppliers`,
  string numbers and booleans, `filters`/`operator`/`field` aliases, conditions written as strings, unknown keys dropped.
- Identical repeated tool calls are skipped. After 2 repeats the loop stops and asks for the answer.
- `clean()` drops unclosed `<think>`, chat-template tokens, and made-up chart image placeholders.

## Default model

The default stays **Nemotron-3-Ultra-550b-a55b**: 10/10 after the fixes, and 8/8 on the two jury questions
(about 8 s each). Super-VL scored the same (10/10 before, jury 6/6) and is about 25 % faster, so it is a good fallback.
On this sample it is not clearly more accurate, so the hardcoded `MODEL_ID` is unchanged.
