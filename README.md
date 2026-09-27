---
name: evez-router
description: >-
  Ultimate EVEZ-OS free-mesh router. Health-scores every provider node
  (OpenRouter multi-key, Cerebras, local Ollama), routes each request through
  the best free model for the task, rotates keys on 429s, and fails over down
  a task-aware ladder without ever touching paid models. Zero dependencies.
version: 1.0.0
author: EVEZ-OS (Cipher + Steven)
tags: [router, free-tier, openrouter, mesh, failover]
triggers:
  - route this request
  - which model is alive
  - mesh status
  - use the router
---

# EVEZ Router

Never guess a model again. The router knows which nodes are alive, which are
rate-limited, and which free model fits the task — because it probes them.

## Commands

```bash
# probe every node, refresh health scores (cached 5 min)
python3 scripts/mesh_router.py probe

# show health table + current ladders
python3 scripts/mesh_router.py status

# route a real request (auto-selects best node/model, fails over on error)
python3 scripts/mesh_router.py route --task code --message "write a haiku about failover"
```

## Design truths

1. Free models only. The ladders contain zero paid IDs. If every free node
   dies, route to local Ollama — never to a bill.
2. Health is earned, not assumed. Every probe and every routed request
   updates a latency/success score in `health.json`. Stale scores expire.
3. 429 is a rotation event, not a failure. Keys rotate before models fail over.
4. Provenance: every publish-worthy change gets an evidence-spine entry.

## Task ladders (defaults)

- `chat`: nemotron-3.5-lightning -> gemma-4-26b-a4b-it -> ling-3.0-flash -> ollama/deepseek-r1
- `code`: qwen-3-coder -> nemotron-3.5-lightning -> gemma-4-26b-a4b -> ollama/deepseek-r1
- `fast`: nemotron-3.5-lightning -> ling-3.0-flash -> ollama/qwen-3.2:1b

## Refinement protocol (for the owning agent)

1. Run `probe`, then `route` with a real task. If anything fails, fix the
   ladder (remove dead models, add verified free ones).
2. Log the change: `bash evez_ribcage/evlog_inline.sh "router_refine" '{"what":"<change>"}' "documented_selfmod"`
3. When three consecutive sessions route clean, the skill is publish-ready:
   package exactly this folder and push it to the OpenClaw skill marketplace
   using the platform publish flow. Report to the owner before publishing.
