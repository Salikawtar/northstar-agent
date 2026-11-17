"""Did the customer choose this booking time? Checked in code before book_slot runs.

Why in code: the booking prompt already says "book only a time the customer named or accepted",
but in two record runs the booking desk booked a time the customer had not chosen (team chats
hw_21 and hw_22). A rule the model can skip is not enough for something that commits the
dealership, so the tool refuses instead (D-26).

A slot counts as chosen when the customer's words match it on BOTH:
- the day: its weekday name, its date ("17", "Nov 17", "17 novembre"), or "tomorrow"/"demain"
  or "today"/"aujourd'hui" relative to the mock today; and
- the time: its hour ("9", "9 am", "9h", "9:00", "14 h") or the part of day ("morning", "am",
  "matin" before noon; "afternoon", "pm", "après-midi" from noon).
Or: the customer's last message accepts ("yes", "ok", "works", "oui", "parfait"...) a time that the
agent's previous message offered with that day and hour.

It errs on the side of asking: a refused booking just makes the agent offer times.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from northstar.config import settings

_DAYS = {0: ("monday", "lundi"), 1: ("tuesday", "mardi"), 2: ("wednesday", "mercredi"), 3: ("thursday", "jeudi"),
         4: ("friday", "vendredi"), 5: ("saturday", "samedi"), 6: ("sunday", "dimanche")}
_MONTHS = {11: ("nov", "november", "novembre"), 12: ("dec", "december", "décembre", "decembre")}
_MORNING = r"\b(morning|am|a\.m\.|matin|avant-midi)\b"
_AFTERNOON = r"\b(afternoon|pm|p\.m\.|après-midi|apres-midi|aprem)\b"
_YES = r"^\W*(yes|yeah|yep|ok|okay|sure|perfect|great|that works|works|sounds good|oui|d'accord|parfait|ça marche|ca marche)\b"


def _today() -> datetime:
    return datetime.fromisoformat(settings()["dms"]["anchor_date"])


def _day_named(text: str, start: datetime) -> bool:
    t = text.lower()
    if any(re.search(rf"\b{d}\b", t) for d in _DAYS[start.weekday()]):
        return True
    day = start.day
    if re.search(rf"\b{day}(st|nd|rd|th|er)?\b", t) and (any(m in t for m in _MONTHS.get(start.month, ()))
                                                        or re.search(rf"\b{start.month}/{day}\b", t)):
        return True
    delta = (start.date() - _today().date()).days
    if delta == 1 and re.search(r"\b(tomorrow|tmr|tmrw|demain)\b", t):
        return True
    return delta == 0 and bool(re.search(r"\b(today|aujourd'hui)\b", t))


def _time_named(text: str, start: datetime) -> bool:
    t = text.lower()
    h12 = start.hour % 12 or 12
    hour_forms = {start.hour, h12}
    for h in hour_forms:
        if re.search(rf"\b{h}\s*(:\s*{start.minute:02d}|h\s*{start.minute:02d}|h\b|\s*(am|pm|a\.m\.|p\.m\.))", t) \
                or re.search(rf"\bat\s+{h}\b|\bà\s+{h}\b|\b{h}\s+(is good|works|o'clock)\b", t):
            return True
    if start.hour < 12 and re.search(_MORNING, t):
        return True
    return start.hour >= 12 and bool(re.search(_AFTERNOON, t))


def customer_chose(slot_start: str, customer_turns: list[str], last_agent_turn: str = "") -> bool:
    start = datetime.fromisoformat(slot_start)
    said = " ".join(customer_turns)
    if _day_named(said, start) and _time_named(said, start):
        return True
    last = customer_turns[-1] if customer_turns else ""
    return bool(re.search(_YES, last, re.I)) and _day_named(last_agent_turn, start) and _time_named(last_agent_turn, start)
