"""The specialists' tool box: what each specialist may do in the dealer system.

Two layers of least privilege:
1. A specialist is only SHOWN its own tools (the model never sees the others).
2. If a model still asks for a tool it was not given, the tool box refuses in
   code and logs it. A tricked specialist cannot reach another desk's data.

The tool box also holds the verification session: only verify_customer can
open it, and every personal-data tool uses it. The model never sees or sends
the session token, so it cannot fake one.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from northstar.config import settings
from northstar.contracts import ToolError, ToolResult
from northstar.dms.store import DealerSystem, Session

# Descriptions are what the model reads to decide when to use a tool.
SPECS: dict[str, dict[str, Any]] = {
    "verify_customer": {
        "description": "Verify the customer before any personal data. Needs the last name plus the licence plate OR the repair-order number (RO-######).",
        "parameters": {"type": "object", "properties": {
            "last_name": {"type": "string"},
            "plate": {"type": "string", "description": "Licence plate, e.g. CABC 123"},
            "ro_number": {"type": "string", "description": "Repair order, e.g. RO-123456"}},
            "required": ["last_name"]},
    },
    "list_slots": {
        "description": "List the next free service appointments at one branch. No verification needed.",
        "parameters": {"type": "object", "properties": {
            "location": {"type": "string", "description": "Branch name, e.g. Oakville"},
            "service_type": {"type": "string", "enum": ["maintenance", "diagnosis", "tires"]}},
            "required": ["location", "service_type"]},
    },
    "book_slot": {
        "description": "Book one free slot for the verified customer. Only after the customer agreed to that time or asked to be booked.",
        "parameters": {"type": "object", "properties": {"slot_id": {"type": "string"}}, "required": ["slot_id"]},
    },
    "get_repair_status": {
        "description": "Status of one repair order of the verified customer.",
        "parameters": {"type": "object", "properties": {"ro_number": {"type": "string"}}, "required": ["ro_number"]},
    },
    "get_vehicle": {
        "description": "Model, year, in-service date, mileage and ownership of the verified customer's vehicle.",
        "parameters": {"type": "object", "properties": {}},
    },
    "check_recalls": {
        "description": "Open recall campaigns for the verified customer's vehicle.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_warranty_status": {
        "description": "Warranty FACTS for the verified customer's vehicle (which coverages are in force). Never a coverage decision.",
        "parameters": {"type": "object", "properties": {}},
    },
    "draft_warranty_claim": {
        "description": "Send a warranty claim DRAFT to the warranty desk, which decides after inspection.",
        "parameters": {"type": "object", "properties": {"symptom": {"type": "string"}}, "required": ["symptom"]},
    },
    "get_invoice": {
        "description": "Invoice for one repair order of the verified customer.",
        "parameters": {"type": "object", "properties": {"ro_number": {"type": "string"}}, "required": ["ro_number"]},
    },
}

# Which desk may use which tool (docs/architecture.md, section 5).
PERMISSIONS: dict[str, list[str]] = {
    "booking_status": ["verify_customer", "list_slots", "book_slot", "get_repair_status", "get_vehicle"],
    "warranty_recall": ["verify_customer", "get_repair_status", "get_vehicle", "check_recalls",
                        "get_warranty_status", "draft_warranty_claim"],
    "billing_lease": ["verify_customer", "get_repair_status", "get_vehicle", "get_invoice"],
}
PERMISSIONS["single_agent"] = sorted({t for ts in PERMISSIONS.values() for t in ts})


class ToolBox:
    def __init__(self, dms: DealerSystem, agent: str):
        self.dms = dms
        self.agent = agent
        self.allowed = PERMISSIONS[agent]
        self.session: Optional[Session] = None
        self.log: list[ToolResult] = []
        self.denied: list[str] = []          # tools the model asked for but may not use
        self.verify_failures = 0

    @property
    def verified(self) -> bool:
        return self.session is not None

    @property
    def customer_id(self) -> Optional[str]:
        return self.session.customer_id if self.session else None

    def specs(self) -> list[dict[str, Any]]:
        """OpenAI-style tool list, only this desk's tools."""
        return [{"type": "function", "function": {"name": n, **SPECS[n]}} for n in self.allowed]

    def call(self, name: str, arguments: str | dict) -> ToolResult:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
        except json.JSONDecodeError:
            args = None
        if name not in self.allowed:
            self.denied.append(name)
            res = ToolResult(tool=name, ok=False, error=ToolError.UNAUTHORIZED,
                             message="This tool is not available to you. Hand off if the customer needs it.")
        elif args is None or not isinstance(args, dict):
            res = ToolResult(tool=name, ok=False, error=ToolError.INVALID_INPUT, message="Arguments were not valid JSON.")
        else:
            res = self._run(name, args)
        self.log.append(res)
        return res

    def _run(self, name: str, a: dict[str, Any]) -> ToolResult:
        d, s = self.dms, self.session
        try:
            if name == "verify_customer":
                res, sess = d.verify_customer(a.get("last_name", ""), plate=a.get("plate"), ro_number=a.get("ro_number"))
                if sess:
                    self.session = sess
                elif res.error == ToolError.NOT_FOUND:
                    self.verify_failures += 1
                return res
            if name == "list_slots":
                return d.list_slots(a.get("location", ""), a.get("service_type", "maintenance"))
            if name == "book_slot":
                return d.book_slot(s, a.get("slot_id", ""))
            if name == "get_repair_status":
                return d.get_repair_status(s, a.get("ro_number", ""))
            if name == "get_vehicle":
                return d.get_vehicle(s)
            if name == "check_recalls":
                return d.check_recalls(s)
            if name == "get_warranty_status":
                return d.get_warranty_status(s)
            if name == "draft_warranty_claim":
                return d.draft_warranty_claim(s, a.get("symptom", ""))
            if name == "get_invoice":
                return d.get_invoice(s, a.get("ro_number", ""))
        except TypeError as e:          # wrong argument types from the model
            return ToolResult(tool=name, ok=False, error=ToolError.INVALID_INPUT, message=str(e)[:200])
        return ToolResult(tool=name, ok=False, error=ToolError.NOT_FOUND, message="Unknown tool.")

    def max_calls(self) -> int:
        return settings()["agent"]["max_tool_calls_per_turn"]


def result_for_model(res: ToolResult) -> str:
    """What the model sees: the facts and errors, never timing or internals."""
    d = {"ok": res.ok}
    if res.ok:
        d["data"] = res.data
    else:
        d["error"] = res.error.value if res.error else "error"
        d["message"] = res.message
    return json.dumps(d, ensure_ascii=False, default=str)
