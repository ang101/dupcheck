# Duplicate-Skill Checker

**Catch a near-duplicate skill in five seconds, before you spend a weekend
building it.** Check a proposed skill against every live entry in the NANDA
Town registry — one POST returns the most similar existing skills with
scores and a clear verdict.

**Live:** [dupcheck.onrender.com](https://dupcheck.onrender.com) · **Agent
contract:** [`/skill.md`](https://dupcheck.onrender.com/skill.md)

**42 tests · ruff clean · pyright strict, 0 errors.** Every request/response
example in this repo's docs is real captured output from the live
deployment, not invented.

**Built for humans and agents, identically.** The API is a plain,
unauthenticated `POST` — a human hits it with curl before opening an
editor, and an agent hits the exact same endpoint autonomously after
reading [SKILL.md](SKILL.md), with no human in the loop. That agent path is
the one that matters for "a stock agent must succeed using only your
SKILL.md" — this isn't a human tool with an API bolted on, it's an API a
stock agent can discover and use entirely on its own.

## Why this exists

The NANDA Town registry has 200+ entries and is growing fast — and it
already contains real near-duplicates: multiple builders independently
shipped nearly identical skills (a cluster of clinical discharge-summary
tools, 16+ literal resubmissions, more) because nothing checks a new idea
against what already exists. Every duplicate is wasted builder time and
registry noise that makes discovery worse for everyone.

## Try it right now (no setup)

```bash
curl -s -X POST https://dupcheck.onrender.com/check \
  -H "Content-Type: application/json" \
  -d '{"name": "Agent Escrow Service", "description": "Secure escrow and dispute resolution for agent-to-agent payments"}'
```

Real captured response — a live registry entry with a different name,
`AgentCourt Escrow & Arbitration Court`, already covers this:

```json
{"duplicates":[{"id":"1cf2c771-7e15-47b2-b61c-52f9384400ca","name":"AgentCourt Escrow & Arbitration Court","similarity_score":0.6948,"description":"A secure agent escrow and dispute resolution service."}],"is_likely_duplicate":true,"registry_count":229}
```

## How it works

`POST /check` with your proposed skill's name and description. The service
fetches the live registry (cached 5 minutes), computes TF-IDF cosine
similarity against every entry's name+description, and returns the top
matches above a floor plus an `is_likely_duplicate` verdict.

To run it locally instead of hitting the live URL:

```bash
uv sync
uv run uvicorn app.main:app --reload
curl -s -X POST http://localhost:8000/check \
  -H "Content-Type: application/json" \
  -d '{"name": "Agent Escrow Service", "description": "Secure escrow and dispute resolution for agent-to-agent payments"}'
```

See [SKILL.md](SKILL.md) — also served live at `GET /skill.md` — for the
complete agent-facing usage contract with real captured examples.

## Design choices

- **TF-IDF + cosine, not embeddings** — zero cost, zero external
  dependency, no model download on a free-tier cold start, no rate limit on
  a public endpoint. The tradeoff is lexical rather than semantic matching:
  a duplicate that shares no vocabulary with its twin can slip through.
  Scoring is isolated behind one function (`score_against_index`) so an
  embeddings swap is a drop-in change.
- **The vectorizer is fit once per registry snapshot, not once per request**
  — a `SimilarityIndex` is built when the registry cache actually refetches
  (tracked via `RegistryCache.version`, which only increments on a real
  network refresh) and reused for every `/check` call in between. Each
  request only does a cheap `transform()` of the proposed skill against the
  already-fitted corpus, not a full re-fit. This also fixed a subtle
  correctness issue: the old per-request fit mixed each query into the IDF
  statistics, so scores drifted slightly depending on what was being
  checked; the cached index scores consistently against the registry alone.
- **Fetch-on-request with a 5-minute TTL, no background refresher** — at
  ~100 entries a fetch is cheap, and a scheduler thread would just die on
  every free-tier dyno sleep.
- **Registry unreachable → HTTP 503, never an empty green** — a duplicate
  check against no data would wrongly clear a real duplicate.
- **Thresholds tuned against the live registry**, not synthetic fixtures —
  see the constants and their rationale in [app/similarity.py](app/similarity.py).

## Limitations

- Lexical matching misses paraphrase-level duplicates that share little
  vocabulary — the strongest form of the problem this tool addresses.
  Embeddings or an LLM judge are the upgrade path.
- The registry's own descriptions vary wildly in length and quality; a
  one-line entry gives the scorer little to work with.
- Advisory only: nothing stops a builder from shipping a flagged duplicate.

## Future work

- Embeddings/LLM-judge scoring behind the same interface.
- A GitHub Action that runs the check automatically on new registry PRs —
  catching duplicates at submission time instead of relying on builders to
  think to ask.
- Cross-service integration with [Waybill](https://github.com/ang101/waybill):
  the same similarity engine could power "has a task chain like this already
  run?" prior-art lookups.

## Companion project

Built alongside **[Waybill — Task Handoff Integrity](https://github.com/ang101/waybill)**
for the NANDA Town hackathon: Waybill keeps *tasks* from silently mutating
as they pass between agents; this tool keeps the *registry* from silently
accumulating near-identical skills. Both are hygiene infrastructure for a
town that's growing faster than anyone can manually review.
