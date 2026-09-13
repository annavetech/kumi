# Review before shipping

A read-only quality pass on code that already works. You call the reviewer directly and get back a ranked findings list, nothing is edited.

## What you type

```
/tiiu review the new orders dashboard component before I ship it
```

## What happens

**tiiu** reviews. Its discipline is read-only, checklist-driven, findings ranked by severity, never edit.

> Read `orders-dashboard.component.ts` and its template. Findings, ranked:
>
> 1. **(high)** The `orders$` subscription in `ngOnInit` is never unsubscribed and there is no `takeUntilDestroyed` / async pipe, it leaks on every navigation away. Move the stream to the template with `| async`, or tie it to the destroy signal.
> 2. **(medium)** `trackBy` is missing on the `*ngFor` over rows, so the whole list re-renders on any change. Add a `trackByOrderId`.
> 3. **(low)** The filter input triggers a request per keystroke. A `debounceTime(200)` on the value stream would cut the traffic without changing behaviour.
>
> No correctness or security issues. Structure and typing are consistent with the other dashboard components.

## The point

The reviewer read the code and returned a ranked list, it did not change a single line. Severity ordering means you act on the leak first and the debounce last, or ship as is and decide yourself. Because the review is read-only, you stay in control of what actually changes; if you want the fixes applied, that is a separate call to the implementer (`/liis`).
