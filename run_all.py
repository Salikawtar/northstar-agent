"""One entry point for the whole project.

    python run_all.py            # run every stage that is built so far
    python run_all.py datagen    # replay the data-generation run and compare it with the dataset
    python run_all.py dms        # just rebuild the mock dealer system
    python run_all.py results    # reproduce every key result from the recordings (no key, no cost)
    python run_all.py evaluate   # final evaluation on the 40 test chats: 8 setups, graded, tables (Phase 4)
    python run_all.py finetune   # three-router comparison on the test chats (Phase 5)
    python run_all.py economics  # cost model, break-even points and memo numbers (Phase 6)
    python run_all.py record     # after a prompt or tool change: make the missing model calls (needs a key)
    python run_all.py test       # run the test suite

Stages are added here as each phase is built, so "python run_all.py" always
reproduces every result in the report (code criterion: single command).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))


def stage_dms():
    from northstar.dms import generate
    generate.main()


def stage_datagen():
    """Replay the recorded generation run and compare it with the dataset (no key, no network)."""
    for args in (["-m", "northstar.datagen.pipeline", "--jobs", "data/source/generation/jobs_designed.jsonl",
                  "--generations", "data/source/generation/generations_v3_conv.jsonl", "--seed", "42",
                  "--out", "outputs/datagen"],
                 ["-m", "northstar.datagen.export", "--diff"],
                 ["-m", "northstar.datagen.split", "--rebuild"],
                 ["-m", "northstar.datagen.diversity"]):
        subprocess.check_call([sys.executable, *args], cwd=ROOT, env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})


RESULT_COMMANDS = [
    ["-m", "northstar.agent.router", "--split", "validation"],
    ["-m", "northstar.agent.specialist", "--agent", "booking_status", "--split", "validation"],
    ["-m", "northstar.agent.specialist", "--agent", "warranty_recall", "--split", "validation"],
    ["-m", "northstar.agent.specialist", "--agent", "billing_lease", "--split", "validation"],
    ["-m", "northstar.agent.pipeline", "--split", "validation"],
    ["-m", "northstar.agent.baseline", "--split", "validation"],
    ["-m", "northstar.agent.scenarios"],
    ["-m", "northstar.guardrails.evaluate"],
    ["-m", "northstar.guardrails.redteam"],
]
# One change at a time, to back each desk's model and effort choice with a result (docs/prompt_log.md).
COMPARISON_COMMANDS = [
    ["-m", "northstar.agent.specialist", "--agent", "booking_status", "--split", "validation", "--model", "large"],
    ["-m", "northstar.agent.specialist", "--agent", "warranty_recall", "--split", "validation", "--effort", "high"],
    ["-m", "northstar.agent.specialist", "--agent", "billing_lease", "--split", "validation", "--model", "small", "--effort", "low"],
]

# Phase 5: the two prompted routers on the 40 test chats, for the three-router comparison.
FINETUNE_BASELINE_COMMANDS = [
    ["-m", "northstar.agent.router", "--split", "test", "--model", "small"],
    ["-m", "northstar.agent.router", "--split", "test", "--model", "large"],
]


def stage_results():
    """Reproduce every key result from the recorded model calls: no key, no cost, same numbers.

    The key is removed from the environment on purpose, so this stage can never spend money.
    If a recording is missing (a prompt changed and nobody ran it yet), the command stops and
    says which one: run `python run_all.py record` once with a key, then this stage reproduces it."""
    _run(RESULT_COMMANDS + COMPARISON_COMMANDS, keep_key=False)
    print("\nAll results reproduced from recordings: outputs/results/")


def _run(commands, keep_key: bool):
    import os
    env = {k: v for k, v in os.environ.items() if keep_key or k != "OPENROUTER_API_KEY"}
    env["PYTHONPATH"] = str(ROOT / "src")
    # The model client also reads the key from .env, so removing it from the environment is not enough:
    # replay mode is forced explicitly for reproduction runs.
    env["NORTHSTAR_LLM_MODE"] = "auto" if keep_key else "replay"
    for args in commands:
        print(f"\n--- python {' '.join(args)}")
        subprocess.check_call([sys.executable, *args], cwd=ROOT, env=env)


# Phase 4: every setup on the 40 test chats, graded by rules and the model grader, plus the development
# run on validation and the grader's self-consistency check (src/northstar/evaluation/).
EVALUATION_COMMANDS = [
    ["-m", "northstar.evaluation", "--split", "validation", "--setups", "full_agent", "full_agent_before_fixes"],
    ["-m", "northstar.evaluation"],
    ["-m", "northstar.evaluation", "consistency"],
    ["-m", "northstar.evaluation", "check"],          # grader vs the team's hand labels (waits for the sheet)
]


def stage_evaluate():
    """Final evaluation, replayed from the recordings (no key, no cost). Tables: src/northstar/evaluation/results/."""
    _run(EVALUATION_COMMANDS, keep_key=False)


def stage_record():
    """Make the model calls that are not recorded yet (needs OPENROUTER_API_KEY; recorded calls stay free).
    Run once after a prompt or tool change; then `results` reproduces everything at no cost."""
    import os
    try:                                   # the key usually lives in .env, as the README says
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("record needs OPENROUTER_API_KEY in .env or in the environment (see .env.example).")
    _run(RESULT_COMMANDS + COMPARISON_COMMANDS + FINETUNE_BASELINE_COMMANDS + EVALUATION_COMMANDS, keep_key=True)


def stage_finetune():
    """Three-router comparison (Phase 5). Prompted routers are replayed from the recordings.
    The fine-tuned router is rerun if its checkpoint is on this machine (1.1 GB, not in git);
    otherwise its committed test results are used. Training itself needs a GPU:
    python -m northstar.finetune.train_router select, then final (see src/northstar/finetune/README.md)."""
    _run(FINETUNE_BASELINE_COMMANDS, keep_key=False)
    if (ROOT / "models" / "finetuned_router" / "weights.pt").exists():
        _run([["-m", "northstar.agent.router", "--split", "test", "--model", "finetuned"],
              ["-m", "northstar.finetune.compare", "--collect"]], keep_key=False)
    else:
        print("No local checkpoint: building the comparison from the committed test results.")
        _run([["-m", "northstar.finetune.compare"]], keep_key=False)
    _run([["-m", "northstar.finetune.breakeven"]], keep_key=False)
    if (ROOT / "src" / "northstar" / "finetune" / "results" / "datasize_runs.csv").exists():
        _run([["-m", "northstar.finetune.datasize"]], keep_key=False)


def stage_economics():
    """Cost model (Phase 6): reads the evaluation and fine-tune results, writes src/northstar/economics/results/."""
    _run([["-m", "northstar.economics"]], keep_key=False)


def stage_test():
    code = subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    if code:
        sys.exit(code)


# Order matters: later stages use earlier outputs.
STAGES = {
    "datagen": stage_datagen,
    "dms": stage_dms,
    "results": stage_results,      # agent (Phase 2) and guardrails (Phase 3), replayed
    "evaluate": stage_evaluate,    # Phase 4: final evaluation on the test chats, replayed
    "finetune": stage_finetune,    # Phase 5: fine-tuned vs small vs large prompted router
    "economics": stage_economics,  # Phase 6: cost model, break-even, numbers for the memo
    "test": stage_test,
}
# Run on request only, never by default: it spends money (python run_all.py record).
EXTRA = {"record": stage_record}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(STAGES)
    for name in wanted:
        stage = STAGES.get(name) or EXTRA.get(name)
        if stage is None:
            sys.exit(f"Unknown stage '{name}'. Choose from: {', '.join([*STAGES, *EXTRA])}")
        print(f"\n=== {name} ===")
        stage()
