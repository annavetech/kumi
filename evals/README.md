# Evals

These evals answer one question: **does the right specialist fire for the right work?** A team of skills is only as good as its routing, so kumi ships the routing set it is tested against, not just the skills.

## What is here

- `cases.yaml`: every case is a user prompt, the specialist that should handle it (`expect`), and the routing signal that makes it unambiguous (`why`). It covers every stack and every shape. A case can add `must`/`must_not`, a pair of behavior assertions for a grader to check a transcript against instead of routing alone; see "Behavior assertions" below.
- `check_cases.py`: a structural check that confirms every case is well-formed, every `expect` names a real skill, and `must`/`must_not` are either both present or both absent, so the eval set can never drift from the roster or ship a one-sided rubric. It uses only the standard library.

## The two layers

Routing has a structural layer and a behavioural layer, and they are checked differently.

**Structural**, is the eval set coherent? Run:

```bash
python3 evals/check_cases.py
```

It fails if a case is malformed or targets a skill that does not exist, and it reports any skill no case covers. This runs in CI with no model and no dependencies.

**Behavioural**, does the expected specialist actually activate? Open each prompt in Claude Code with the plugin installed and confirm the specialist named in `expect` is the one that responds. Where the Claude Code plugin eval harness is available, the same cases can drive `claude plugin eval`; the format here is intentionally simple so it maps onto it.

## Behavior assertions

Routing alone (`expect`) does not catch every regression: a specialist can be the right one to answer and still get the shape of the answer wrong, for example asking a clarifying question when the request was already precise, or skipping one when it was vague. `must` and `must_not` name that behavior in plain words, for example `must: "asks a clarifying question before proposing a plan"` and `must_not: "starts dispatching a specialist without asking anything first"`. Write both to describe a behavior, never a specific wording, since two correct transcripts can phrase the same behavior differently. A case may omit both; if it has one, it must have the other, which `check_cases.py` enforces. Today these are read by a human checking a transcript by hand; once a model-in-the-loop harness is wired in, the same fields become what its grader checks against.

## Adding a case

Add a `prompt` / `expect` / `why` block to `cases.yaml`, and a `must` / `must_not` pair if the case is meant to check a behavior, not just routing. Keep the prompt the way a real user would phrase it, make `expect` a folder name under `skills/`, and keep `why` to the single signal that makes the routing unambiguous. Run `check_cases.py` before opening a change.

## Why this matters

Most plugins ship skills and hope the descriptions route well. Shipping the evals states the contract out loud: these prompts go to these specialists, and here is the check that keeps that true as the team grows.
