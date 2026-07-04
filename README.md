# Decision Engine

A single-file FastAPI + Jinja2 + Tailwind dashboard that triages 5 incoming
business requests: auto-approving small refunds, kicking off onboarding for
new customers, prioritizing VIPs, and handling two edge cases (manager
unavailable, both staff busy) — plus a manual override path and a full
decision audit trail.

There is no database. Everything lives in in-memory Python lists/dicts in
`main.py` and is (re)computed once at process start.

## Setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/

## Deploy (free, live link)

This app has a real Python backend (manual override + export routes), so it
needs a host that runs Python — not static hosting like GitHub Pages.
[Render](https://render.com) has a free tier and reads `render.yaml`
automatically:

1. Push this repo to GitHub (already done if you're reading this from the repo).
2. Go to [render.com](https://render.com) → **New** → **Blueprint** → connect
   this GitHub repo. Render detects `render.yaml` and configures the build/start
   commands automatically.
3. Click **Apply** / **Create**. After the build finishes you'll get a public
   URL like `https://decision-engine.onrender.com` — share that link directly.

(`Procfile` + `runtime.txt` are included too, for Railway/Heroku-style hosts
that don't read `render.yaml`.)

## Project structure

```
main.py                        # FastAPI app, decision engine, all routes
templates/index.html           # Single-page dashboard (Tailwind via CDN)
requirements.txt
render.yaml                    # Render deploy config (build/start commands)
Procfile / runtime.txt         # Deploy config for Railway/Heroku-style hosts
.claude/skills/self-review/    # Project skill: audits this app against the
  skill.md                     # challenge requirements and generates a
                                # PASS/FAIL report
```

## Decision logic

Processed once at startup, VIP requests first, then FIFO:

1. **Refund < $100** → auto-approved, no human involved (`System (Automated)`).
2. **Refund >= $100** → escalated to the manager; if the manager is
   unavailable, held as **Pending Manager** with a 2-hour escalation timeout
   *(edge case)*.
3. **New customer** → automated onboarding sequence, no staff assignment.
4. **VIP** → priority assignment to the first available staff member.
5. **Regular, needs staff** → assigned FIFO to the first available staff
   member; if both staff are busy, **queued** with an estimated wait time
   *(edge case)*.

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Dashboard: requests table, stats, filters, decision history, flash messages |
| POST | `/override/{request_id}` | Manual override (see below) — redirects back to `/` |
| GET | `/export` | Downloads the full audit trail as `decision_report_<timestamp>.json` |

## Improvements added on top of the base dashboard

**1. Decision History Log** — every automated decision and every manual
override is appended to an in-memory `decision_history` list and rendered as
a scrollable, most-recent-first table at the bottom of the page (Timestamp,
Request ID, Customer, Action, Assigned To, Reasoning). Manual entries carry
a visible `MANUAL_OVERRIDE` tag.

**2. Manual Override (human-in-the-loop)** — each request's detail view
(click any row, or its "🔧 Override" button) has a small form with four
actions: assign to staff member 1, assign to staff member 2, escalate to
manager, or mark completed. Applying one:
- Updates that request's status/decision/reasoning immediately.
- Recomputes staff busy/available state from the current request list
  (`recalculate_staff_busy()`), so overriding a request off a staff member
  frees them up again.
- Logs a `MANUAL_OVERRIDE` row to the decision history.
- Redirects back to `/` with a dismissible "✅ Override applied" flash
  banner (auto-fades after 5s).

**3. Export Report** — the "📊 Export Report" button (top of the page) hits
`GET /export`, which returns a JSON file (`Content-Disposition: attachment`)
containing: every request's current state, the full decision history, staff
and manager status, and summary counts (`auto_approved_count`,
`onboarding_count`, `assigned_count`, `escalated_count`, `queued_count`,
`completed_count`).

## Manually verified during development

- `POST /override/5` with `action=assign_staff_1` → 303 redirect with flash,
  status flips to `Assigned`, staff busy state updates.
- `POST /override/3` with `action=mark_completed` → status flips to
  `Completed`.
- `POST /override/1` with `action=escalate_manager` → status flips to
  `Escalated`, frees the staff member that had been assigned.
- `POST /override/<id>` with an unknown action → `400`.
- `POST /override/999` (nonexistent id) → `404`.
- `GET /export` → valid JSON with all 6 top-level keys and correct summary
  counts.

## 90-second demo script

1. **(0:00–0:15)** Load the dashboard. Point out the 5 requests, the stat
   tiles, and the red "Attention needed" banner calling out the two active
   edge cases.
2. **(0:15–0:35)** Click Emma Johnson's row (refund < $100) → show the
   green **Auto-Approved** badge and reasoning. Click Tom Rivera (new
   customer) → show the **Onboarding** badge.
3. **(0:35–0:55)** Click Michael Brown (refund >= $100) → show **Pending
   Manager** with the escalation timeout. Click Lisa Wang → show **Queued**
   with the estimated wait time. Point at the staff/manager availability
   panel to explain why.
4. **(0:55–1:15)** Open Lisa Wang's override form, assign her to a staff
   member, submit → show the flash message, the status flip, and the new
   row at the top of the Decision History log tagged `MANUAL_OVERRIDE`.
5. **(1:15–1:30)** Click "📊 Export Report" → show the downloaded JSON
   (requests, history, staff, summary stats). Toggle dark mode to close.

## Self-review

Run the `self-review` skill (`.claude/skills/self-review/skill.md`) against
this project to get a PASS/FAIL audit against the original challenge
requirements, the 3 improvements, and demo readiness.
