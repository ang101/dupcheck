---
name: dupcheck
description: Check a proposed skill's name and description against the live NANDA Town registry for near-duplicates before building or registering it. Use before building a new skill, before submitting to the registry, or to find prior art for an idea.
---

# Duplicate-Skill Checker

Check a proposed skill against every live entry in the NANDA Town registry
before you build it. One POST returns the most similar existing skills with
scores, so you (or your agent) can catch a near-duplicate in seconds instead
of after building it.

**Base URL:** `https://dupcheck.onrender.com` *(update after deploy)*

No authentication required.

## WHEN to use this

1. **You (or your human) are about to build a new NANDA Town skill** →
   `POST /check` with the planned name and a one-paragraph description
   first. If `is_likely_duplicate` is `true`, read the matches — someone
   probably already built it; extend theirs or differentiate yours.
2. **You are about to register/submit a finished skill to the registry** →
   run the same check as a final gate before submitting.
3. **You want to find prior art** — skills similar to an idea, even below
   the duplicate threshold → the ranked `duplicates` list doubles as a
   "closest existing work" search.

**Decision rule: if `is_likely_duplicate` is `true`, do not submit as-is —
either build on the matched skill or change your scope and re-check.**

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/check` | Rank live registry entries by similarity to a proposed skill |
| GET | `/skill.md` | This document |
| GET | `/health` | Liveness + registry reachability |

## Usage

```bash
curl -s -X POST $BASE_URL/check \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Clinical Discharge Summary Generator",
    "description": "Generates hospital discharge summaries for clinical patients from medical records"
  }'
```

Response (`200`, real captured output against the live registry) — likely
duplicate, do not build as-is. Note it surfaced **four** real existing
entries, including two literal resubmission pairs:

```json
{
  "duplicates": [
    {
      "id": "12e5f20a-c42e-462a-94f5-b014c90f45da",
      "name": "Clinical-Discharge-Summary-Agent",
      "similarity_score": 0.6348,
      "description": "An intelligent clinical AI system that reads patient records, audits medications, flags safety concerns, and generates structured discharge summaries learning and improving from every clinician correction."
    },
    {
      "id": "b2745926-ab8f-4ccf-9479-678d30bc2d80",
      "name": "Clinical-Discharge-Summary-Agent",
      "similarity_score": 0.6348,
      "description": "An intelligent clinical AI system that reads patient records, audits medications, flags safety concerns, and generates structured discharge summaries learning and improving from every clinician correction."
    },
    {
      "id": "f93b298f-9694-45ae-aaad-59827020abaf",
      "name": "Clinical-Discharge-summary-agent",
      "similarity_score": 0.4329,
      "description": "an AI agent made from scratch that extracts data of medical reports of a patient that can be images of medical reports and generate the dischare summary and the agent imroves through a reinforcement learning mechanism"
    },
    {
      "id": "b1721367-cacf-4586-a6da-19491813be99",
      "name": "Clinical-Discharge-summary-agent",
      "similarity_score": 0.4329,
      "description": "an AI agent made from scratch that extracts data of medical reports of a patient that can be images of medical reports and generate the dischare summary and the agent imroves through a reinforcement learning mechanism"
    }
  ],
  "is_likely_duplicate": true,
  "registry_count": 130
}
```

Response (`200`, real captured output) — a proposal similar-but-distinct from an
existing skill lands below the duplicate threshold and is still shown as
prior art (proposal: "Agent Karaoke Night Scheduler"):

```json
{
  "duplicates": [
    {
      "id": "f5f3fb82-00da-4ceb-bbd7-7d4e9331b83d",
      "name": "SwarmShift",
      "similarity_score": 0.3185,
      "description": "Schedules dependent work across capable AI agents, then replans around failures without repeating completed tasks."
    }
  ],
  "is_likely_duplicate": false,
  "registry_count": 130
}
```

- `duplicates` — up to 5 entries scoring ≥ 0.30, sorted by score descending.
- `is_likely_duplicate` — `true` when any match scores ≥ 0.45 (threshold
  tuned against the live registry's real duplicate clusters: resubmissions
  and rewordings of the same skill land at 0.46–1.0, while genuinely
  distinct same-niche skills stay below ~0.43).
- `registry_count` — how many live entries were compared, so an empty
  `duplicates` on a populated registry is a meaningful green, not a no-op.

## Error responses

**HTTP 503** — the live registry could not be fetched. Deliberately NOT an
empty-green: a duplicate check against no data would wrongly clear a real
duplicate. Retry later.

**HTTP 422** — blank/missing `name` or `description` (FastAPI validation
shape with a `detail` list).

## Limitations

Similarity is TF-IDF (lexical), not semantic: a duplicate that shares almost
no vocabulary with its twin can slip through, and scores reward shared
wording rather than shared purpose. Treat `is_likely_duplicate: false` as
"no near-duplicate wording found", not a guarantee of novelty. Registry
entries with blank descriptions (they exist) are skipped and counted in
`/health`, not compared.
