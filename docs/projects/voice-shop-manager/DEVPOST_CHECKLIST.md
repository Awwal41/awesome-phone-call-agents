# Devpost submission checklist

Use when the demo branch is ready for hackathon submission.

## Required

- [ ] **Pull request URL** — open PR from `Awwal41/awesome-phone-call-agents` → `CALLE-AI/awesome-phone-call-agents` on `feat/shop-voice-manager`
- [ ] **Demo video** (~3 min, public YouTube or Vimeo) — record from [`DEMO_WALKTHROUGH.md`](./DEMO_WALKTHROUGH.md)
- [ ] **CALL-E account email** — address used at heycall-e.com signup

## Optional

- [ ] **Live demo URL** — not required; CLI demo is sufficient
- [ ] **CALL-E Feedback Survey** — for Most Valuable Feedback prize eligibility

## PR description template

```markdown
## Summary
Voice Shop Manager — voice-first AI business manager for informal African/Indian retailers.
CALL-E check-in calls → structured inventory/sales JSON → weekly insights.
Demo mode runs with fixtures (no live call required).

## Contribution area
- Skill: skills/shop-voice-checkin/
- App: apps/python/shop-voice-manager/ (demo runner; Rajput/Aranwa extending)

## Test plan
- [ ] python scripts/validate_repository.py
- [ ] cd apps/python/shop-voice-manager && python client.py --request example_request.json --weekly-summary
```

## Video outline

See [`DEMO_SCRIPT.md`](./DEMO_SCRIPT.md).

## Status

**Task A5:** Ready for manual Devpost form fill once PR + video exist. Demo repo work is complete.
