"""Tests for the model client. A fake transport stands in for OpenRouter, so
these run offline and cost nothing. Each test name says which rule it protects."""
import pytest
from pydantic import BaseModel

from northstar.llm import BudgetExceeded, CacheMiss, LLMClient, LLMError

MSG = [{"role": "user", "content": "hello"}]


class Fake:
    """Pretend OpenRouter. Raises the errors in `fail` first, then answers."""
    def __init__(self, answers=("hi",), fail=(), cost=0.01):
        self.answers, self.fail, self.cost, self.calls = list(answers), list(fail), cost, 0

    def __call__(self, req):
        self.calls += 1
        if self.fail:
            raise self.fail.pop(0)
        text = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return {"text": text, "input_tokens": 10, "output_tokens": 5, "cost_usd": self.cost}


def client(tmp_path, fake, **kw):
    return LLMClient(mode="live", transport=fake, cache_dir=tmp_path, sleep=lambda s: None, **kw)


def test_answer_and_usage_are_recorded(tmp_path):
    c = client(tmp_path, Fake())
    r = c.chat("small-model", MSG)
    assert r.text == "hi" and c.usage.calls == 1 and c.usage.cost_usd == pytest.approx(0.01)


def test_same_call_twice_is_served_from_cache_and_not_paid_twice(tmp_path):
    fake = Fake()
    c = client(tmp_path, fake)
    c.chat("small-model", MSG)
    r = c.chat("small-model", MSG)
    assert r.from_cache and fake.calls == 1 and c.usage.spent_usd == pytest.approx(0.01)


def test_replay_mode_answers_from_recording_without_network(tmp_path):
    client(tmp_path, Fake(["recorded"])).chat("small-model", MSG)
    r = LLMClient(mode="replay", cache_dir=tmp_path).chat("small-model", MSG)
    assert r.text == "recorded" and r.from_cache


def test_replay_mode_never_calls_the_network(tmp_path):
    with pytest.raises(CacheMiss):
        LLMClient(mode="replay", cache_dir=tmp_path).chat("small-model", MSG)


def test_failed_call_is_retried_then_succeeds(tmp_path):
    fake = Fake(fail=[TimeoutError("slow")])
    assert client(tmp_path, fake).chat("small-model", MSG).text == "hi" and fake.calls == 2


def test_gives_up_after_max_retries(tmp_path):
    fake = Fake(fail=[TimeoutError()] * 10)
    with pytest.raises(LLMError):
        client(tmp_path, fake).chat("small-model", MSG)
    assert fake.calls == 3  # 1 try + max_retries (2)


def test_spending_limit_stops_the_run(tmp_path):
    c = client(tmp_path, Fake(cost=0.6), budget_usd=1.0)
    c.chat("m", [{"role": "user", "content": "a"}])
    c.chat("m", [{"role": "user", "content": "b"}])
    with pytest.raises(BudgetExceeded):
        c.chat("m", [{"role": "user", "content": "c"}])


class Label(BaseModel):
    request_type: str


def test_broken_json_gets_one_correction(tmp_path):
    fake = Fake(answers=["not json", '{"request_type": "parts_order"}'])
    out, _ = client(tmp_path, fake).chat_json("m", MSG, Label)
    assert out.request_type == "parts_order" and fake.calls == 2


def test_json_in_code_fences_is_accepted(tmp_path):
    out, _ = client(tmp_path, Fake(['```json\n{"request_type": "book_service"}\n```'])).chat_json("m", MSG, Label)
    assert out.request_type == "book_service"


def test_still_broken_json_raises_clear_error(tmp_path):
    with pytest.raises(LLMError):
        client(tmp_path, Fake(["nope", "still nope"])).chat_json("m", MSG, Label)
