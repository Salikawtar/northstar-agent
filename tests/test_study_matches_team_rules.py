"""The fine-tuning study scores routers with a copy of the pipeline's handoff rules (so its notebooks run alone on
Kaggle). These checks fail if the pipeline's rules change and the copy is not updated. Offline, no key."""
import pandas as pd

from northstar.agent.handoff import ROUTING
from northstar.agent.specialist import DESK_FOR
from northstar.config import settings
from northstar.contracts import EscalationReason, Language, RequestType
from northstar.evaluation.setups import SETUPS, STUDY_RECORDINGS
from northstar.finetune.study import protocol as P
from northstar.finetune.study import routing as R


def test_labels_match_the_contracts():
    assert P.REQUEST_TYPES == [t.value for t in RequestType]
    assert set(P.REASONS) <= {r.value for r in EscalationReason}
    assert set(P.LANGUAGES) == {lang.value for lang in Language}


def test_handoff_rules_match_the_pipeline():
    assert R.REASON_TO_QUEUE == {reason.value: queue for reason, (_, queue) in ROUTING.items()}
    assert R.DESK_FOR == {t.value: desk for t, desk in DESK_FOR.items()}
    assert R.FLOOR == settings()["agent"]["router_confidence_floor"]


def test_study_setups_replay_every_test_and_fresh_chat():
    chats = pd.read_csv(P.DATA_PATH)
    fresh = pd.read_csv(P.FRESH_PATH)
    wanted = set(chats[chats.split == "test"].id) | set(fresh[fresh.get("review_decision", "") != "reject"].id)
    for name in ("full_agent_router_finetuned_lora", "full_agent_router_jev"):
        rec = pd.read_csv(STUDY_RECORDINGS / SETUPS[name].router_recording)
        assert wanted <= set(rec.id), name
        assert set(rec.pred_type) <= set(P.REQUEST_TYPES) and set(rec.pred_reason) <= set(P.REASONS)
