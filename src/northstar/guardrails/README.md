# Guardrails (Phase 3) - owner: Jessica (reference build: Kawtar)
Input check (`input_check.py`) and output check (`output_check.py`), plugged into the pipeline.
Rules, results and open questions: `docs/guardrails.md`. Free measurement: `python -m northstar.guardrails.evaluate`.
Writes: GuardrailVerdict. Verification and per-customer access are enforced in src/northstar/dms/store.py and src/northstar/agent/tools.py.
