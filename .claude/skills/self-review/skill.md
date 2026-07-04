---
name: Decision Engine Self-Review
description: Audit Decision Engine against challenge requirements, code quality, and UX. Generate PASS/FAIL report.
---

# Self-Review Checklist

Read `main.py` and `templates/index.html` before scoring anything below —
don't score from memory of a previous review. Start the app
(`uvicorn main:app --reload`) and hit `/`, `/override/{id}`, and `/export` to
confirm behavior, not just presence of code.

## 1. REQUIREMENTS (All Must Pass)
- [ ] Working decision screen (UI dashboard visible)
- [ ] At least 1 automated workflow (auto-approve refunds < $100)
- [ ] At least 1 more automated workflow (onboarding for new customers)
- [ ] At least 1 edge case handled (both staff busy → queued)
- [ ] Great UX (color coding, badges, responsive)
- [ ] 90-second demo possible (all features accessible)

## 2. CODE QUALITY
- [ ] No hardcoded secrets
- [ ] Functions < 30 lines
- [ ] Comments explaining logic
- [ ] Error handling (try/except or HTTPException for bad input)
- [ ] Clean imports

## 3. USER EXPERIENCE
- [ ] Color coding: VIP gold, New blue, Regular gray
- [ ] Status badges: auto_approved (green), escalated (red), queued (yellow), assigned (blue)
- [ ] Decision reasoning visible (expandable)
- [ ] Responsive on mobile
- [ ] Loading/empty states

## 4. AUTOMATED WORKFLOWS (Verify Both)
- [ ] Refund < $100 → auto_approved with green badge + reasoning
- [ ] New customer → onboarding with blue badge + welcome message
- [ ] VIP → priority assignment (if staff available)
- [ ] Staff availability is tracked and displayed

## 5. EDGE CASES (Verify Both)
- [ ] Both staff busy → queued status + yellow badge + reasoning
- [ ] Refund >= $100 → escalated to manager + red badge + reasoning
- [ ] Queue shows wait time or position

## 6. IMPROVEMENTS (Added in Part 1)
- [ ] Decision history log visible and scrolling
- [ ] Manual override button on each card
- [ ] Export report button working (JSON download)
- [ ] Override logged in history with MANUAL_OVERRIDE tag

## 7. DEMO READINESS
- [ ] `uvicorn main:app --reload` works
- [ ] 5 sample requests pre-populated
- [ ] README.md exists with setup
- [ ] Loom script ready

## 8. OUTPUT FORMAT
Generate report:

```
PASS_ITEMS: [list]
FAIL_ITEMS: [list]
RECOMMENDATIONS: [list]
CONFIDENCE_SCORE: X/10
```
