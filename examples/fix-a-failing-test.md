# Fix a failing test

A single, specific bug. You know it is a debugging task, so you call the debugger directly instead of going through the coordinator.

## What you type

```
/siim the TestProjectList test panics with a nil pointer dereference
```

## What happens

**siim** debugs. Its discipline is reproduce first, find the root cause, touch only the broken path, verify the failure is gone.

**1. Reproduce.**

> Ran `go test -run TestProjectList`. Confirmed: panic, nil pointer at `handler.go:88`, in `ListProjects` when `store` is nil.

**2. Find the root cause.**

> The test constructs the handler with `NewHandler()` but never sets `store`. In production `store` is injected by the server bootstrap, so the nil is only reachable from this test's construction path. The bug is the test's setup, not the handler, the handler correctly assumes an injected store, and every other test injects one.

**3. Fix only the broken path.**

> Set `store` in the test's setup the same way the sibling tests do, one line, using the existing `newTestStore()` helper. Did not add a nil check to the handler: that would hide a real misconfiguration in production behind a silent empty result.

**4. Verify.**

> `go test -run TestProjectList` passes. Full package `go test ./...` still green. `go vet` clean.

## The point

The debugger did not reach for the handler code, and did not add a defensive nil check to "make the error go away". It found where the nil actually came from, the test setup, and fixed that, leaving the production assumption intact. Touching only the broken path is the whole discipline.
