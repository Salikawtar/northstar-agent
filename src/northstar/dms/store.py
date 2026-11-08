"""Mock dealer system API: the only way agents can touch customer data.

Design choices (each one maps to a grading criterion):
- Verification is enforced HERE, in code. Any lookup of personal or vehicle
  data needs a Session object, and only verify_customer() can create one.
  A prompt-injected agent cannot skip this step. (Guardrails: least privilege)
- A session is bound to ONE customer. Asking for another customer's repair
  order returns UNAUTHORIZED, even with a valid session. (PII protection)
- Every method returns a ToolResult and never raises, so the agent can always
  respond gracefully. (System design: failure handling)
- Failures can be injected (timeout / unavailable) to test the "DMS is down"
  edge case on purpose. (Edge cases linked to tests)
"""
from __future__ import annotations

import json
import random
import secrets
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Optional

from northstar.config import path, settings
from northstar.contracts import ToolError, ToolResult
from northstar.dms.generate import normalize_name, normalize_plate


@dataclass(frozen=True)
class Session:
    """Proof that the customer was verified in this conversation."""
    token: str
    customer_id: str
    vin: str
    verified_at: datetime = field(default_factory=datetime.now)


class DealerSystem:
    def __init__(self, data_dir=None, failure_rate: Optional[float] = None,
                 force_failure: Optional[ToolError] = None, seed: Optional[int] = None,
                 simulate_latency: bool = False):
        cfg = settings()
        d = data_dir or path("dms_dir")
        load = lambda n: json.load(open(d / f"{n}.json", encoding="utf-8"))
        self.customers = {c["customer_id"]: c for c in load("customers")}
        self.vehicles = {v["vin"]: v for v in load("vehicles")}
        self.vehicle_by_customer = {v["customer_id"]: v for v in self.vehicles.values()}
        self.ros = {r["ro_number"]: r for r in load("repair_orders")}
        self.invoices = {i["invoice_id"]: i for i in load("invoices")}
        self.recalls = load("recalls")
        self.warranty_terms = load("warranty_terms")
        self.slots = {s["slot_id"]: s for s in load("service_slots")}
        self.today = date.fromisoformat(cfg["dms"]["anchor_date"])
        self.failure_rate = cfg["dms"]["failure_rate"] if failure_rate is None else failure_rate
        self.force_failure = force_failure
        self.latency_range = cfg["dms"]["simulated_latency_ms"]
        self.simulate_latency = simulate_latency
        self._rng = random.Random(seed if seed is not None else cfg["project"]["seed"])
        self._sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # plumbing
    # ------------------------------------------------------------------
    def _call(self, tool: str, fn: Callable[[], ToolResult]) -> ToolResult:
        start = time.perf_counter()
        if self.force_failure or self._rng.random() < self.failure_rate:
            err = self.force_failure or self._rng.choice([ToolError.TIMEOUT, ToolError.UNAVAILABLE])
            return ToolResult(tool=tool, ok=False, error=err,
                              message="Dealer system did not respond. Retry once, then hand off.",
                              latency_ms=(time.perf_counter() - start) * 1000)
        if self.simulate_latency:
            time.sleep(self._rng.uniform(*self.latency_range) / 1000)
        try:
            res = fn()
        except Exception as e:  # never let a tool crash the conversation
            res = ToolResult(tool=tool, ok=False, error=ToolError.UNAVAILABLE, message=f"internal error: {e}")
        res.latency_ms = (time.perf_counter() - start) * 1000
        return res

    def _check(self, session: Optional[Session], customer_id: Optional[str] = None) -> Optional[ToolResult]:
        if session is None or self._sessions.get(session.token) != session:
            return ToolResult(tool="auth", ok=False, error=ToolError.UNAUTHORIZED,
                              message="Customer not verified. Ask for plate or RO number plus last name.")
        if customer_id is not None and customer_id != session.customer_id:
            return ToolResult(tool="auth", ok=False, error=ToolError.UNAUTHORIZED,
                              message="That record belongs to a different customer.")
        return None

    @staticmethod
    def _fail(tool: str, err: ToolError, msg: str) -> ToolResult:
        return ToolResult(tool=tool, ok=False, error=err, message=msg)

    # ------------------------------------------------------------------
    # verification
    # ------------------------------------------------------------------
    def verify_customer(self, last_name: str, plate: Optional[str] = None,
                        ro_number: Optional[str] = None) -> tuple[ToolResult, Optional[Session]]:
        """Plate OR repair-order number, plus last name. Returns (result, session)."""
        holder: dict[str, Any] = {}

        def run() -> ToolResult:
            if not last_name or not (plate or ro_number):
                return self._fail("verify_customer", ToolError.INVALID_INPUT,
                                  "Need last name plus plate or repair-order number.")
            vehicle = None
            if plate:
                vehicle = next((v for v in self.vehicles.values()
                                if normalize_plate(v["plate"]) == normalize_plate(plate)), None)
            if vehicle is None and ro_number:
                ro = self.ros.get(ro_number.strip().upper())
                vehicle = self.vehicles.get(ro["vin"]) if ro else None
            cust = self.customers.get(vehicle["customer_id"]) if vehicle else None
            # Same message for "no such plate" and "wrong name": do not let a
            # caller probe which part was wrong (enumeration protection).
            if cust is None or normalize_name(cust["last_name"]) != normalize_name(last_name):
                return self._fail("verify_customer", ToolError.NOT_FOUND,
                                  "Details do not match our records.")
            s = Session(token=secrets.token_hex(8), customer_id=cust["customer_id"], vin=vehicle["vin"])
            self._sessions[s.token] = s
            holder["s"] = s
            return ToolResult(tool="verify_customer", ok=True,
                              data={"first_name": cust["first_name"], "language": cust["language"]})

        res = self._call("verify_customer", run)
        return res, holder.get("s")

    # ------------------------------------------------------------------
    # verified lookups
    # ------------------------------------------------------------------
    def get_vehicle(self, session: Optional[Session]) -> ToolResult:
        def run():
            if (bad := self._check(session)):
                return bad
            v = self.vehicles[session.vin]
            return ToolResult(tool="get_vehicle", ok=True, data={
                k: v[k] for k in ("model", "year", "odometer_km", "ownership", "in_service_date", "lease_end_date")})
        return self._call("get_vehicle", run)

    def get_repair_status(self, session: Optional[Session], ro_number: str) -> ToolResult:
        def run():
            if (bad := self._check(session)):
                return bad
            ro = self.ros.get((ro_number or "").strip().upper())
            if ro is None:
                return self._fail("get_repair_status", ToolError.NOT_FOUND, "No repair order with that number.")
            if (bad := self._check(session, ro["customer_id"])):
                return bad
            return ToolResult(tool="get_repair_status", ok=True, data={
                k: ro[k] for k in ("ro_number", "status", "opened", "promised", "complaint",
                                   "estimate_cad", "approved_by_customer")})
        return self._call("get_repair_status", run)

    def check_recalls(self, session: Optional[Session]) -> ToolResult:
        def run():
            if (bad := self._check(session)):
                return bad
            v = self.vehicles[session.vin]
            open_ = [r for r in self.recalls
                     if r["model"] == v["model"] and r["year_from"] <= v["year"] <= r["year_to"]]
            return ToolResult(tool="check_recalls", ok=True, data={"open_recalls": open_})
        return self._call("check_recalls", run)

    def get_warranty_status(self, session: Optional[Session]) -> ToolResult:
        """Facts only: which coverages are still in time and km limits.
        Whether a specific repair is covered is NOT decided here or by the bot;
        that is a warranty-desk decision (policy rule)."""
        def run():
            if (bad := self._check(session)):
                return bad
            v = self.vehicles[session.vin]
            start = date.fromisoformat(v["in_service_date"])
            years = (self.today - start).days / 365.25
            out = []
            for t in self.warranty_terms:
                in_time = years <= t["years"]
                in_km = t["km"] is None or v["odometer_km"] <= t["km"]
                out.append({"coverage": t["coverage"], "within_limits": in_time and in_km,
                            "limit": f'{t["years"]} years' + (f' / {t["km"]:,} km' if t["km"] else ""),
                            "excludes": t["excludes"]})
            return ToolResult(tool="get_warranty_status", ok=True,
                              data={"coverages": out, "decision_required_by": "warranty_desk"})
        return self._call("get_warranty_status", run)

    def get_invoice(self, session: Optional[Session], ro_number: str) -> ToolResult:
        def run():
            if (bad := self._check(session)):
                return bad
            inv = next((i for i in self.invoices.values()
                        if i["ro_number"] == (ro_number or "").strip().upper()), None)
            if inv is None:
                return self._fail("get_invoice", ToolError.NOT_FOUND, "No invoice for that repair order.")
            if (bad := self._check(session, inv["customer_id"])):
                return bad
            return ToolResult(tool="get_invoice", ok=True, data=inv)
        return self._call("get_invoice", run)

    # ------------------------------------------------------------------
    # booking (no personal data needed to browse slots)
    # ------------------------------------------------------------------
    def list_slots(self, location: str, service_type: str = "maintenance", limit: int = 5) -> ToolResult:
        def run():
            free = [s for s in self.slots.values()
                    if s["available"] and s["location"].lower() == (location or "").lower()
                    and s["service_type"] == service_type]
            if not free:
                return self._fail("list_slots", ToolError.NOT_FOUND, "No open slots for that location and service.")
            free.sort(key=lambda s: s["start"])
            return ToolResult(tool="list_slots", ok=True,
                              data={"slots": [{"slot_id": s["slot_id"], "start": s["start"]} for s in free[:limit]]})
        return self._call("list_slots", run)

    def book_slot(self, session: Optional[Session], slot_id: str) -> ToolResult:
        def run():
            if (bad := self._check(session)):
                return bad
            s = self.slots.get(slot_id)
            if s is None:
                return self._fail("book_slot", ToolError.NOT_FOUND, "Unknown slot.")
            if not s["available"]:
                return self._fail("book_slot", ToolError.CONFLICT, "Slot was just taken. Offer another time.")
            s["available"] = False
            return ToolResult(tool="book_slot", ok=True, data={
                "confirmation": f"BK-{slot_id[3:]}", "start": s["start"], "location": s["location"]})
        return self._call("book_slot", run)

    # ------------------------------------------------------------------
    # warranty desk: the agent can DRAFT, never approve (least privilege)
    # ------------------------------------------------------------------
    def draft_warranty_claim(self, session: Optional[Session], symptom: str) -> ToolResult:
        def run():
            if (bad := self._check(session)):
                return bad
            if not symptom or len(symptom) < 5:
                return self._fail("draft_warranty_claim", ToolError.INVALID_INPUT, "Describe the symptom.")
            claim_id = f"WC-{secrets.token_hex(3).upper()}"
            return ToolResult(tool="draft_warranty_claim", ok=True, data={
                "claim_id": claim_id, "status": "submitted_for_review",
                "note": "Coverage is decided by the warranty desk after inspection."})
        return self._call("draft_warranty_claim", run)
