# Evals

These evals answer one question: **does the right specialist fire for the right work?** A team of skills is only as good as its routing, so kumi ships the routing set it is tested against, not just the skills.

## What is here

- `cases.yaml`: every case is a user prompt, the specialist that should handle it (`expect`), and the routing signal that makes it unambiguous (`why`). It covers every stack and every shape.
- `check_cases.py`: a structural check that confirms every case is well-formed and every `expect` names a real skill, so the eval set can never drift from the roster. It uses only the standard library.

## The two layers

Routing has a structural layer and a behavioural layer, and they are checked differently.

**Structural**, is the eval set coherent? Run:

```bash
python3 evals/check_cases.py
```

It fails if a case is malformed or targets a skill that does not exist, and it reports any skill no case covers. This runs in CI with no model and no dependencies.

**Behavioural**, does the expected specialist actually activate? Open each prompt in Claude Code with the plugin installed and confirm the specialist named in `expect` is the one that responds. Where the Claude Code plugin eval harness is available, the same cases can drive `claude plugin eval`; the format here is intentionally simple so it maps onto it.

## Adding a case

Add a `prompt` / `expect` / `why` block to `cases.yaml`. Keep the prompt the way a real user would phrase it, make `expect` a folder name under `skills/`, and keep `why` to the single signal that makes the routing unambiguous. Run `check_cases.py` before opening a change.

## Why this matters

Most plugins ship skills and hope the descriptions route well. Shipping the evals states the contract out loud: these prompts go to these specialists, and here is the check that keeps that true as the team grows.
