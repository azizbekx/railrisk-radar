# AGENTS.md

Notes for coding agents working on RailRisk Radar.

- Python: use the repo venv (`.venv/bin/python`). Keys come from `.env` (`NEBIUS_API_KEY`, `TAVILY_API_KEY`). Never print or commit them.
- The LLM is always NVIDIA Nemotron 3 Ultra on Nebius Token Factory, hardcoded as `MODEL_ID` in `core/llm.py`.
- The data chat (views/chat.py) runs `core.agent.run(..., tools=agent.DATA_TOOLS, system=agent.DATA_SYSTEM)`;
  ground truth for the 10,000 suppliers lives in `core/dataset.py`.

## Evals

The chat assistant has an eval harness in `evals/`. Every check is computed from `core/dataset.py`, so
expected values follow the data rather than hard-coded numbers.

```bash
# offline robustness tests for the agent loop (fake LLM, no credits)
.venv/bin/python -m evals.test_agent_offline
.venv/bin/python -m evals.test_sourcing_offline   # Find suppliers pipeline (core/sourcing.py), no credits

# live evals against Nemotron on Nebius Token Factory (each run costs credits)
.venv/bin/python -m evals.chat_evals --list                    # cases and available Nemotron models
.venv/bin/python -m evals.chat_evals                           # default model, all 10 cases (~25 LLM calls)
.venv/bin/python -m evals.chat_evals --case jury --repeat 3    # the two jury questions, 3 times each
.venv/bin/python -m evals.chat_evals --model all               # every Nemotron chat model
.venv/bin/python -m evals.chat_evals --model nvidia/nemotron-3-super-120b-a12b --case typo_id -v
.venv/bin/python -m evals.chat_evals --rescore evals/results/<file>.json   # re-apply changed checks, no LLM calls
```

- Cases live in `evals/cases.py`: the two jury questions, the four chat presets, and realistic buyer questions
  (sourcing filter, group averages, data the set does not have, name lookup, typo'd ID, 20-supplier comparison).
  Each case sends the prompt exactly as views/chat.py does, with the `(Buyer's current shortlist: ...)` suffix.
- Every case also runs the generic checks: no error steps, a real answer, every SUPP_ ID exists, numbers stated
  next to a supplier ID match the dataset, no `<think>`/tool-call markup leaks, and no more than 8 LLM calls.
- The output is a pass/fail table per model with median latency and LLM calls. Full traces (raw model replies, tool
  args and results) are saved to `evals/results/*.json`, which is gitignored. `evals/RESULTS.md` has the latest summary.
- `--model X` changes the model only inside the harness (it patches `llm.model`), never in the app's own selection.
- When you change `core/agent.py`, `core/llm.py` or `DATA_SYSTEM`, run the offline tests, then at least
  `--case jury --repeat 2` on the default model.
