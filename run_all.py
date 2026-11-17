"""One entry point for the whole project.

    python run_all.py            # run every stage that is built so far
    python run_all.py datagen    # replay the data-generation run and compare it with the dataset
    python run_all.py dms        # just rebuild the mock dealer system
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


def stage_test():
    code = subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    if code:
        sys.exit(code)


# Order matters: later stages use earlier outputs.
STAGES = {
    "datagen": stage_datagen,
    "dms": stage_dms,
    # "agent":     Phase 2
    # "guardrails": Phase 3
    # "evaluate":  Phase 4
    # "finetune":  Phase 5
    # "economics": Phase 6
    "test": stage_test,
}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(STAGES)
    for name in wanted:
        if name not in STAGES:
            sys.exit(f"Unknown stage '{name}'. Choose from: {', '.join(STAGES)}")
        print(f"\n=== {name} ===")
        STAGES[name]()
