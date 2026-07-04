"""
Decision Engine — a small FastAPI app that triages incoming business requests.

Run with:  uvicorn main:app --reload

There is no database. All state (staff, manager, and the 5 sample requests)
lives in memory as plain Python dicts/lists and is processed once, at startup,
by run_decision_engine(). The single "/" route just renders the result.
"""

import json
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException
from fastapi.requests import Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Decision Engine")
templates = Jinja2Templates(directory="templates")

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------

# Two front-line staff members who handle complaints/inquiries.
# Alex starts busy (already on a call) so the sample data naturally produces
# both an immediate VIP assignment AND a "both staff busy" queue scenario.
STAFF = [
    {"name": "Alex Kim", "busy": True},
    {"name": "Jordan Patel", "busy": False},
]

# The manager who must approve big refunds. Marked unavailable on purpose to
# demonstrate the "manager unavailable" edge case.
MANAGER = {"name": "Morgan Lee", "available": False}

# The 5 incoming requests. Mix of VIP / new / regular customers and
# refund / complaint / inquiry request types, per the assignment brief.
REQUESTS = [
    {
        "id": 1,
        "customer": "Sarah Chen",
        "customer_type": "vip",
        "request_type": "complaint",
        "request_text": "Received a damaged product, demands immediate replacement.",
        "amount": 0.0,
    },
    {
        "id": 2,
        "customer": "Tom Rivera",
        "customer_type": "new",
        "request_type": "inquiry",
        "request_text": "Asking about premium plan features and pricing.",
        "amount": 0.0,
    },
    {
        "id": 3,
        "customer": "Emma Johnson",
        "customer_type": "regular",
        "request_type": "refund",
        "request_text": "Requesting a refund for a wrong-size item.",
        "amount": 45.00,
    },
    {
        "id": 4,
        "customer": "Michael Brown",
        "customer_type": "regular",
        "request_type": "refund",
        "request_text": "Requesting a refund for defective electronics.",
        "amount": 350.00,
    },
    {
        "id": 5,
        "customer": "Lisa Wang",
        "customer_type": "regular",
        "request_type": "complaint",
        "request_text": "Complaint about a 2-week shipping delay.",
        "amount": 0.0,
    },
]

# Status -> badge color + short label, used by the template.
STATUS_STYLES = {
    "Auto-Approved": {"color": "good", "label": "Auto-Approved"},
    "Onboarding": {"color": "info", "label": "Onboarding"},
    "Assigned": {"color": "assigned", "label": "Assigned"},
    "Escalated": {"color": "serious", "label": "Escalated"},
    "Pending Manager": {"color": "critical", "label": "Pending Manager"},
    "Queued": {"color": "warning", "label": "Queued"},
    "Completed": {"color": "completed", "label": "Completed"},
}

CUSTOMER_TYPE_STYLES = {
    "vip": {"label": "VIP", "color": "vip"},
    "new": {"label": "New", "color": "new"},
    "regular": {"label": "Regular", "color": "regular"},
}

# Improvement 1: Decision History Log — every automated decision and every
# manual override gets appended here, newest entries shown first in the UI.
decision_history: list[dict] = []


def log_decision(result: dict, tag: str = "AUTOMATED") -> None:
    """Append one row to the audit trail (decision_history)."""
    decision_history.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "request_id": result["id"],
            "customer": result["customer"],
            "action": result["decision"],
            "assigned_to": result["assigned_to"],
            "reasoning": result["reasoning"],
            "tag": tag,
        }
    )


def run_decision_engine(requests, staff, manager):
    """
    Applies the business's decision logic to every incoming request and
    returns a new list of fully-annotated request dicts (status, decision,
    assigned_to, reasoning, etc.) ready for display.

    Processing order: VIP requests are evaluated first (priority), then the
    rest in their original (FIFO) order — mirroring how a real dispatcher
    would triage an inbox.
    """
    # Work on copies of the staff/manager state so repeated calls stay
    # deterministic (each call starts from the same "Alex is busy" baseline).
    staff_state = [dict(s) for s in staff]
    manager_state = dict(manager)

    vip_first = sorted(requests, key=lambda r: 0 if r["customer_type"] == "vip" else 1)

    results_by_id = {}
    queue_position = 0

    for req in vip_first:
        result = dict(req)
        result["is_edge_case"] = False
        result["edge_case_type"] = None
        result["wait_time"] = None
        result["escalation_timeout"] = None

        # --- Rule 1: refunds -----------------------------------------------
        if req["request_type"] == "refund":
            if req["amount"] < 100:
                # Automated workflow: small refunds need no human review.
                result["status"] = "Auto-Approved"
                result["decision"] = "Auto-Approved Refund"
                result["assigned_to"] = "System (Automated)"
                result["is_auto"] = True
                result["reasoning"] = (
                    f"Refund amount ${req['amount']:.2f} is under the $100 "
                    f"auto-approval threshold and the customer ({req['customer_type']}) "
                    "is in good standing. The system auto-approved this refund "
                    "with no manual intervention."
                )
            else:
                # Refunds >= $100 require manager sign-off.
                if manager_state["available"]:
                    result["status"] = "Escalated"
                    result["decision"] = "Escalated to Manager"
                    result["assigned_to"] = manager_state["name"]
                    result["is_auto"] = False
                    result["reasoning"] = (
                        f"Refund amount ${req['amount']:.2f} meets/exceeds the $100 "
                        f"threshold, so it was escalated to manager "
                        f"{manager_state['name']} for approval."
                    )
                else:
                    # Edge case: manager unavailable for approval > $100.
                    result["status"] = "Pending Manager"
                    result["decision"] = "Escalated — Awaiting Manager"
                    result["assigned_to"] = f"{manager_state['name']} (Unavailable)"
                    result["is_auto"] = False
                    result["is_edge_case"] = True
                    result["edge_case_type"] = "manager_unavailable"
                    result["escalation_timeout"] = "2 hours"
                    result["reasoning"] = (
                        f"Refund amount ${req['amount']:.2f} requires manager approval "
                        f"(>= $100 threshold), but {manager_state['name']} is currently "
                        "unavailable. Request is held as 'Pending Manager' with a "
                        "2-hour auto-escalation timeout, after which it will be "
                        "re-routed to a backup approver."
                    )

        # --- Rule 2: new customers ------------------------------------------
        elif req["customer_type"] == "new":
            # Automated workflow: new customers get an onboarding sequence
            # instead of being routed to a busy staff member.
            result["status"] = "Onboarding"
            result["decision"] = "Send Onboarding Sequence"
            result["assigned_to"] = "System (Automated)"
            result["is_auto"] = True
            result["reasoning"] = (
                f"{req['customer']} is a new customer, so the automated onboarding "
                "email/sequence was triggered instead of a manual staff assignment."
            )

        # --- Rule 3: everyone else needs a staff member ---------------------
        else:
            available = [s for s in staff_state if not s["busy"]]
            is_vip = req["customer_type"] == "vip"

            if available:
                chosen = available[0]
                chosen["busy"] = True
                result["status"] = "Assigned"
                result["is_auto"] = False
                if is_vip:
                    result["decision"] = "Priority Assignment"
                    result["assigned_to"] = chosen["name"]
                    result["reasoning"] = (
                        f"{req['customer']} is a VIP customer, so this request "
                        f"received priority routing and was assigned immediately "
                        f"to the first available staff member, {chosen['name']}."
                    )
                else:
                    result["decision"] = "Assigned (FIFO)"
                    result["assigned_to"] = chosen["name"]
                    result["reasoning"] = (
                        f"{req['customer']} is a regular customer. Staff member "
                        f"{chosen['name']} was available and assigned on a "
                        "first-in-first-out basis."
                    )
            else:
                # Edge case: both staff members are busy -> queue with an
                # estimated wait time instead of leaving the request stuck.
                queue_position += 1
                wait_minutes = queue_position * 15
                result["status"] = "Queued"
                result["assigned_to"] = f"Queue position {queue_position}"
                result["is_auto"] = False
                result["is_edge_case"] = True
                result["edge_case_type"] = "queue"
                result["wait_time"] = f"~{wait_minutes} minutes"
                staff_names = ", ".join(s["name"] for s in staff_state)
                if is_vip:
                    result["decision"] = "Queued (VIP Priority)"
                    result["reasoning"] = (
                        f"{req['customer']} is VIP, but both staff members "
                        f"({staff_names}) are currently busy. Placed at the front "
                        f"of the queue with an estimated wait of ~{wait_minutes} minutes."
                    )
                else:
                    result["decision"] = "Queued"
                    result["reasoning"] = (
                        f"Both staff members ({staff_names}) are currently busy. "
                        f"{req['customer']} was placed in queue position "
                        f"{queue_position} with an estimated wait of "
                        f"~{wait_minutes} minutes."
                    )

        log_decision(result, tag="AUTOMATED")
        results_by_id[req["id"]] = result

    # Return results in the original display order (id ascending), not the
    # VIP-first processing order.
    return [results_by_id[r["id"]] for r in requests]


# Run the engine once at import time; the dashboard is a fixed snapshot of
# this sample data (no forms/DB to mutate it at runtime).
PROCESSED_REQUESTS = run_decision_engine(REQUESTS, STAFF, MANAGER)


def build_stats(processed):
    """Small KPI counts shown at the top of the dashboard."""
    return {
        "total": len(processed),
        "auto_approved": sum(1 for r in processed if r["status"] in ("Auto-Approved", "Onboarding")),
        "assigned": sum(1 for r in processed if r["status"] == "Assigned"),
        "pending_manager": sum(1 for r in processed if r["status"] == "Pending Manager"),
        "queued": sum(1 for r in processed if r["status"] == "Queued"),
    }


def build_export_summary(processed):
    """Summary counts for the exported JSON report (Improvement 3)."""
    return {
        "auto_approved_count": sum(1 for r in processed if r["status"] == "Auto-Approved"),
        "onboarding_count": sum(1 for r in processed if r["status"] == "Onboarding"),
        "assigned_count": sum(1 for r in processed if r["status"] == "Assigned"),
        "escalated_count": sum(1 for r in processed if r["status"] in ("Escalated", "Pending Manager")),
        "queued_count": sum(1 for r in processed if r["status"] == "Queued"),
        "completed_count": sum(1 for r in processed if r["status"] == "Completed"),
    }


def recalculate_staff_busy():
    """
    Improvement 2 (Manual Override): recompute each staff member's busy flag
    from scratch, based only on the 5 tracked requests currently "Assigned"
    to them. Called after every override so freeing/reassigning a request
    immediately reflects on staff availability.
    """
    for s in STAFF:
        s["busy"] = any(
            r["assigned_to"] == s["name"] and r["status"] == "Assigned"
            for r in PROCESSED_REQUESTS
        )


@app.get("/")
def dashboard(request: Request, flash: str | None = None, flash_customer: str | None = None):
    history_sorted = sorted(
        decision_history,
        key=lambda d: (d["timestamp"], d["request_id"]),
        reverse=True,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "requests": PROCESSED_REQUESTS,
            "stats": build_stats(PROCESSED_REQUESTS),
            "status_styles": STATUS_STYLES,
            "customer_type_styles": CUSTOMER_TYPE_STYLES,
            "staff": STAFF,
            "manager": MANAGER,
            "decision_history": history_sorted,
            "flash": flash,
            "flash_customer": flash_customer,
        },
    )


# ---------------------------------------------------------------------------
# Improvement 2: Manual Override (human-in-the-loop)
# ---------------------------------------------------------------------------
OVERRIDE_ACTIONS = {"assign_staff_1", "assign_staff_2", "escalate_manager", "mark_completed"}


@app.post("/override/{request_id}")
def override_request(request_id: int, action: str = Form(...)):
    if action not in OVERRIDE_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown override action: {action}")

    req = next((r for r in PROCESSED_REQUESTS if r["id"] == request_id), None)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")

    # Any manual override resolves whatever automated edge case was present.
    req["is_auto"] = False
    req["is_edge_case"] = False
    req["edge_case_type"] = None
    req["wait_time"] = None
    req["escalation_timeout"] = None

    if action in ("assign_staff_1", "assign_staff_2"):
        staff_member = STAFF[0] if action == "assign_staff_1" else STAFF[1]
        req["status"] = "Assigned"
        req["decision"] = f"Manual Override — Assigned to {staff_member['name']}"
        req["assigned_to"] = staff_member["name"]
        req["reasoning"] = (
            f"A staff member manually reassigned this request to "
            f"{staff_member['name']}, overriding the automated routing decision."
        )
    elif action == "escalate_manager":
        req["status"] = "Escalated"
        req["decision"] = "Manual Override — Escalated to Manager"
        req["assigned_to"] = MANAGER["name"]
        req["reasoning"] = (
            f"A staff member manually escalated this request to "
            f"{MANAGER['name']} for approval, overriding the automated decision."
        )
    elif action == "mark_completed":
        req["status"] = "Completed"
        req["decision"] = "Manual Override — Marked Completed"
        req["reasoning"] = (
            "A staff member manually marked this request as completed."
        )

    recalculate_staff_busy()
    log_decision(req, tag="MANUAL_OVERRIDE")

    redirect_url = f"/?flash=Override applied&flash_customer={quote(req['customer'])}"
    return RedirectResponse(url=redirect_url, status_code=303)


# ---------------------------------------------------------------------------
# Improvement 3: Export Report
# ---------------------------------------------------------------------------
@app.get("/export")
def export_report():
    now = datetime.now(timezone.utc)
    report = {
        "generated_at": now.isoformat(timespec="seconds") + "Z",
        "requests": PROCESSED_REQUESTS,
        "decision_history": decision_history,
        "staff": STAFF,
        "manager": MANAGER,
        "summary_stats": build_export_summary(PROCESSED_REQUESTS),
    }
    filename = f"decision_report_{now.strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=json.dumps(report, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
