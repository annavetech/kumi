# Delegate a whole feature, across stacks

When a request already says exactly what's needed, it doesn't need clarifying questions or an explained plan; it needs the team to just run it. This example is deliberately larger than a single-stack endpoint: it spans a Go API and its React frontend in one request.

## What you type

```
/yui add a "recent activity" feed: a paginated Go endpoint backed by the existing events table, and a React panel that renders it, with tests and a review on both sides
```

## What happens

**yui** reads the request, sees it is precise and spans two stacks plus review, and does not ask anything, it states the plan in one line and dispatches.

> Sequencing: kai designs the endpoint shape and the panel's data contract, jaan builds the Go endpoint, noa builds the React panel against kai's contract, then mart and aki review each side. Go ahead?

**1. kai designs** the endpoint shape and the exact JSON contract the panel will consume, writing both to the shared handoff so jaan and noa build against the same shape without re-deriving it.

**2. jaan implements** the Go endpoint per the spec, with table-driven tests.

**3. noa implements** the React panel against the same contract, once jaan's shape is confirmed in the handoff, with its own component tests.

**4. mart reviews** the Go side; **aki reviews** the React side. Both read-only, both ranked findings.

**yui relays** both review results together. You decide what ships as-is and what goes back for a fix.

## The point

One request named no specialist and asked no permission for the obvious parts. `yui` still confirmed once, in one line, before dispatching four specialists across two stacks and two reviews, and passed the same design contract to both implementers so neither guessed at the other's shape. This is the same coordinator as the plain-language example: it reads the request and matches its own behavior to how much the request already says.
