---
globs: **/*.ts, **/*.tsx, **/*.js, **/*.jsx
---

# TypeScript Error Handling

- Custom error classes extending `Error` (`ApiError`, `ValidationError`).
- Result types for expected failures: `{ ok: true; data: T } | { ok: false; error: E }`.
- Always wrap `async/await` in try/catch — unhandled rejections crash Node.
- React error boundaries for component-level failures.
- Structured project logger, not `console.log`.
- User-facing messages don't leak stack/internals.

```typescript
class ApiError extends Error {
  constructor(message: string, public readonly statusCode: number, public readonly cause?: Error) {
    super(message);
    this.name = "ApiError";
  }
}

try {
  const data = await fetchUser(id);
  return { ok: true, data } as const;
} catch (err) {
  logger.error("fetchUser failed", { userId: id, err });
  return { ok: false, error: "User not found" } as const;
}
```

## Don't

- `catch (e) {}` — silent swallow.
- `catch (e) { return null }` — hides failures.
- `console.error` alone — log AND handle.
