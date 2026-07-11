# How to submit Duplicate-Skill Checker to NANDA Town

Step-by-step guide for the skills-page submission, with every field
pre-filled and copy-paste ready.

## Before you submit — 2-minute pre-flight

Run these and confirm both return healthy output (endpoints are
live-checked by the registry at submission time):

```bash
curl --ssl-no-revoke https://dupcheck.onrender.com/health
# expect: {"status":"ok","registry":"<N> skills cached (<M> malformed entries skipped)"}

curl --ssl-no-revoke https://dupcheck.onrender.com/skill.md
# expect: the full SKILL.md markdown, including the YAML frontmatter block
```

If `/health` reports `"status":"degraded"` — STOP: the live registry is
unreachable from the service. Wait and retry before submitting; a
degraded service will fail the registry's own reachability check.

## The form

Go to **https://nandatown.projectnanda.org/skills** and find the submit
form. Fill in:

| Field | Value (copy-paste) |
|---|---|
| **Skill name** | `Duplicate-Skill Checker` |
| **Your name or team** | Angela Garabet |
| **Email** | agarabet@gmail.com *(private, only visible to the NANDA team)* |
| **GitHub username** | `ang101` |
| **One-line description** | `Check a proposed skill's name and description against the live NANDA Town registry for near-duplicates before building or registering it — catches near-duplicates in seconds instead of after a weekend of building.` |
| **Submission method** | Choose **Hosted link to .md file** |
| **SKILL.md hosted link** | `https://dupcheck.onrender.com/skill.md` |
| **Endpoint URLs** (one per line) | see below |
| **Tags** | `duplicate-detection, registry-hygiene, skill-validation, prior-art, similarity, tf-idf, quality-control, submission-gate, dedup, registry` |

**Endpoint URLs — paste exactly this, one per line:**

```
https://dupcheck.onrender.com/check
https://dupcheck.onrender.com/skill.md
https://dupcheck.onrender.com/health
```

*(`/check` is a POST endpoint with a JSON body — documented fully in
SKILL.md; the registry's reachability checker only needs the concrete
URL, not the request shape.)*

## After submitting

1. Search the skills page for "duplicate" or "dupcheck" and confirm the
   entry appears and shows as reachable.
2. Cross-check against Waybill's own submission (`github.com/ang101/waybill`)
   — both should show as reachable at the same time; if one is up and the
   other isn't, something changed between submissions and is worth
   re-verifying before the final form is due.

## Remaining deadlines (ET)

- **Sat Jul 11, 2:00 PM** — edit window closes; **demo video due**. The
  video covers both Waybill and dupcheck together — see
  `waybill/DEMO_WALKTHROUGH.md` (and the local, not-committed
  `NandaTown/GOLIVE.md`) for the full script; dupcheck's cameo is the
  "how it fits" beat, not a separate video.
- **Sun Jul 12, 2:00 PM** — final Google form due (link on the hackathon
  page). Have ready: both skills-page entries, both repo URLs, the video.

## Quick reference for the form's "why does this matter" free-text field
(if one exists)

Measured against the live registry (219 entries as of 2026-07-10):
16+ pairs of literal resubmissions at similarity 1.0 (TownInspector alone
submitted 4 times), plus a real, live example of two *differently-named*
skills — AgentCheckpoint and AgentGate — that a made-up proposal with zero
word overlap still catches at 0.74-0.78 similarity, purely on function.
Full evidence in `PITCH.md`.
