"""The language-model client and answer parsing, with no network: a fake transport, and replay without a key."""
import pytest

from northstar.finetune.study import baselines as B
from northstar.finetune.study import protocol as P

GOOD = ('{"request_type": "roadside_assistance", "secondary_types": [], "needs_escalation": true, '
        '"escalation_reason": "safety", "confidence": 0.98, "language": "en"}')
JEV = {"request_type": {"type": "choice", "choice": "billing_dispute",
                        "probabilities": {**{k: 0.0 for k in P.REQUEST_TYPES}, "billing_dispute": 1.0}, "confidence": 1.0},
       "escalate": {"type": "noul", "noul": 0.83},
       "language": {"type": "choice", "choice": "fr", "probabilities": {"en": 0.0, "fr": 1.0}},
       "reason": {"type": "choice", "choice": "policy_limit", "probabilities": {"policy_limit": 1.0}}}


def test_router_json_parser():
    assert B.parse_router_json(GOOD)["type"] == "roadside_assistance"
    assert B.parse_router_json("```json\n" + GOOD + "\n```")["esc"] is True
    assert B.parse_router_json(GOOD.replace('"safety"', '"none"')) is None      # escalate needs a reason
    assert B.parse_router_json("not json") is None


def test_jev_parser_good_malformed_refusal():
    j = B.parse_jev(JEV)
    assert j["type"] == "billing_dispute" and j["esc"] is True and j["language"] == "fr"
    with pytest.raises(ValueError):
        B.parse_jev({**JEV, "escalate": {"type": "noul"}})
    assert B.parse_jev({**JEV, "request_type": {"type": "refusal"}})["type"] == "needs_human"


def test_jev_questions_both_versions_come_from_the_team_prompt():
    v1, v2 = B.jev_questions(), B.jev_questions_v2()
    assert list(v1) == list(v2) == ["request_type", "escalate", "language", "reason"]
    assert list(v2["request_type"]["criteria"]) == P.REQUEST_TYPES
    assert len(B.prompt_examples()) == 6
    assert "Worked examples" in v2["reason"]["instructions"] and "Worked examples" not in v1["reason"]["instructions"]
    assert "Only these count" in v2["reason"]["criteria"]["adversarial"]      # the prompt's own attack definition


class FakeNetwork(B.Client):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls = 0

    def _post(self, url, body):
        self.calls += 1
        if url == B.DECISIONS_URL:
            return {"answers": JEV, "usage": {"input_tokens": 900, "output_tokens": 0, "cost": 4e-5}}, 0.2
        return {"choices": [{"message": {"content": GOOD}}], "usage": {"prompt_tokens": 2400, "completion_tokens": 200, "cost": 4e-4}}, 1.0


def test_run_resume_and_replay_without_a_key(tmp_path):
    pool = P.pool(P.load_all()).iloc[:12].reset_index(drop=True)
    live = FakeNetwork("KEY", tmp_path / "cache")
    d = B.run_variant(live, "haiku", pool, "first_message", 0, tmp_path / "preds", workers=2)
    assert len(d) == 12 and not d["fallback"].any() and live.calls == 12
    B.run_variant(live, "jev2", pool, "first_message", 0, tmp_path / "preds", workers=2)
    # no key: everything saved replays, at no cost
    replay = B.Client(None, tmp_path / "cache")
    again = B.run_variant(replay, "haiku", pool, "first_message", 0, tmp_path / "preds_again")
    assert (again["type"] == d["type"]).all() and replay.spent == 0
    # no key and a call never made: stops with a clear error instead of hiding it
    with pytest.raises(B.ReplayMiss):
        B.run_variant(replay, "sonnet", pool, "first_message", 0, tmp_path / "preds_again")


def test_unusable_answers_are_refused_not_saved(tmp_path):
    class Garbage(FakeNetwork):
        def _post(self, url, body):
            return {"choices": [{"message": {"content": "sorry"}}], "usage": {}}, 1.0
    pool = P.pool(P.load_all()).iloc[:10].reset_index(drop=True)
    with pytest.raises(B.ApiError):
        B.run_variant(Garbage("KEY", tmp_path / "c"), "sonnet", pool, "first_message", 0, tmp_path / "p")
    assert not (tmp_path / "p" / "sonnet_first_message_rep0.csv").exists()
