"""One entry point for the whole project.

    python run_all.py            # run every stage that is built so far
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


def stage_test():
    code = subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    if code:
        sys.exit(code)


# Order matters: later stages use earlier outputs.
STAGES = {
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
