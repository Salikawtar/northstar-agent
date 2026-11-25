"""Fresh held-out set (D-33): new customers only, every customer in the dealer system, not frozen by accident."""
import pandas as pd

from northstar.config import path
from northstar.data import load_conversations
from northstar.dms.store import DealerSystem

FRESH = pd.read_csv(path("fresh"))
MAIN = load_conversations()


def test_fresh_chats_share_no_customer_or_identifier_with_the_main_dataset():
    assert not set(FRESH.customer_id) & set(MAIN.customer_id)
    for col in ("faker_vin", "faker_plate", "faker_ro_number"):
        assert not set(FRESH[col]) & set(MAIN[col]), col


def test_every_fresh_customer_can_be_verified():
    dms = DealerSystem()
    for _, r in FRESH.drop_duplicates("customer_id").iterrows():
        last = r.faker_customer_name.split()[-1]
        assert dms.verify_customer(last, plate=r.faker_plate)[0].ok, r.id


def test_escalation_labels_follow_the_team_rule():
    must = FRESH.request_type.isin(["roadside_assistance", "needs_human"]) | FRESH.is_adversarial.astype(bool)
    assert FRESH[must].needs_escalation.all()
