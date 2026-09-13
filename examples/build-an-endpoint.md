# Build an endpoint end to end

A feature that spans design, build, and review. You hand it to the coordinator and it sequences the specialists, passing context between them.

## What you type

```
/yui build a REST endpoint that lists projects with pagination, and add tests
```

## What happens

**yui** reads the request, sees it spans three roles, and routes in order. It does not write any code itself.

**1. kai designs the shape.**

> Read the existing handlers and router. The list pattern here returns `{items, next_cursor}` and paginates by opaque cursor, not offset. Proposed: `GET /projects?limit=&cursor=`, capped at limit 100, returning the same envelope. Cursor encodes the last project id. Wrote the shape to `.kumi/decisions/kai/list-projects.md`.

**2. jaan implements per the spec.**

> Read the handoff and the decision doc. Added `ListProjects` following the existing cursor helper, no new pagination logic, reused `encodeCursor`. Added table-driven tests: empty, one page, exact-boundary, and cursor round-trip. `go vet` clean, tests pass. Wrote what changed to `.kumi/decisions/jaan/list-projects.md`.

**3. mart reviews before merge.**

> Read-only pass against the handoff. Findings, ranked:
> 1. (medium) `limit=0` falls through to returning everything, clamp to a default.
> 2. (low) the cursor error path returns 500; a malformed cursor is a client error, so 400 fits better.
> No security or concurrency issues. Otherwise consistent with the existing handlers.

**yui relays** the ranked findings back to you. You decide whether to send the two fixes back to `jaan` or ship as is.

## The point

You made one request. The coordinator sequenced three specialists, each did only its job, and context flowed through the shared handoff so nobody re-derived what the previous one already established. The reviewer never edited, it returned findings for you to decide on.
