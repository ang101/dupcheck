# Duplicate-Skill Checker
### *Check before you build.*

---

**In one sentence**: POST a proposed skill's name and description, get back
the most similar existing skills with scores and a clear
`is_likely_duplicate` verdict — five seconds instead of a wasted weekend,
usable identically by a human builder or a fully autonomous agent.

---

## The problem: the registry is already full of duplicates

This isn't hypothetical. Measured against the live NANDA Town registry
(229 entries, 2026-07-10), computing pairwise similarity across every
entry finds:

- **16 pairs of literal resubmissions** (similarity exactly 1.0):
  TownInspector appears **4 times**, "Absolutely Anything Is Billable"
  **3 times**, Clinical-Discharge-Summary-Agent twice, plus duplicate
  entries of DelegAuth, Cortexa Firewall, DataFacts Verifier, AgentHall,
  FrugalRoute, EMPIC Weather Demo, AgentPress, and more.
- **A near-duplicate band at 0.45–0.90**: `Testament` vs `TESTAMENT`
  (0.543), `LEX AUTOMATA` vs `lex-automata` (0.462), NIDRA Protocol
  twice (0.861), Agent Reputation Ledger twice (0.762).
- **3 entries with blank descriptions** that can't even be compared.

Every duplicate is wasted builder time and registry noise that makes
discovery worse for everyone — including the judges reviewing it. And it
happens for one simple reason: **nothing checks a new idea against what
already exists.** (Our own team learned this the hard way: our Step 1
hackathon PR was closed as a duplicate of a PR we didn't know existed.)

## The fix: one POST before you build

```
POST /check {"name": "...", "description": "..."}
→ top 5 most-similar existing skills, with scores
→ is_likely_duplicate: true/false
```

Five seconds instead of a wasted weekend. Built for humans and agents
identically — the endpoint doesn't know or care which is calling. A human
runs it with curl before opening an editor; an agent runs the exact same
call autonomously after reading SKILL.md, including an orchestrator
deciding whether to author a brand-new skill for a subtask or delegate to
one that already exists. The agent path is the one that satisfies "a stock
agent must succeed using only your SKILL.md" — this is an API a stock
agent can discover and use on its own, not a human tool with an API bolted
on afterward.

## Evidence it works (real captured output)

**Proof it catches function, not just names.** Proposing a completely
made-up name — `"TaskGuard Preflight"`, sharing zero words with anything in
the registry — with the description *"Pre-action decision API: tells
agents if a task is safe, what is missing, and which option to pick before
they act"* still surfaces two real, differently-named registry skills:
`AgentCheckpoint` (0.78) and `AgentGate` (0.74), both well above the 0.45
duplicate threshold. Neither name overlaps the proposal at all — this is
lexical-on-meaning, not lexical-on-labels.

**Proof it catches literal resubmission clusters.** Proposing *"Clinical
Discharge Summary Generator"* against the live registry surfaces **all
four** existing clinical-discharge entries (including both resubmission
pairs) and returns `is_likely_duplicate: true`. Proposing a genuinely novel
idea returns a clean
`{"duplicates": [], "is_likely_duplicate": false, "registry_count": 229}` —
with the count proving it actually compared against a populated registry.

## Design honesty

- **TF-IDF (lexical), not embeddings** — zero cost, zero external
  dependency, no rate limit on a public endpoint. Thresholds are tuned on
  the real registry's full pairwise distribution (unrelated pairs:
  p95 = 0.10; true duplicates: 0.46–1.0), not synthetic fixtures. The
  limitation is disclosed: a duplicate sharing no vocabulary with its twin
  can slip through. Scoring is isolated behind one function, so embeddings
  are a drop-in upgrade.
- **Registry unreachable → HTTP 503, never a silent empty green** — a
  duplicate check against no data would wrongly clear a real duplicate.
- **Malformed registry entries are skipped, counted, and reported** via
  `/health` — one builder's bad submission can't take the service down.

## Where this goes

The natural next step is a **GitHub Action on the registry repo**: every
new skill submission gets an automatic duplicate-check comment, catching
the TownInspector-submitted-4-times problem at the source instead of
relying on builders to think to ask.

## Companion project

Built alongside **[Waybill — Task Handoff Integrity](https://github.com/ang101/waybill)**:
Waybill keeps *tasks* from silently mutating as they pass between agents;
this keeps the *registry* from silently accumulating near-identical
skills. Two sides of the same thesis — a growing agent town needs hygiene
infrastructure that scales past manual review.
