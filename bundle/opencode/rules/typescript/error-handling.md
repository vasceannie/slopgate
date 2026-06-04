
# TypeScript Error Handling

## Do This

- **Custom error classes**: Extend `Error` with specific types (`ApiError`, `ValidationError`)
- **Error boundaries**: React error boundaries for component-level failures
- **Result types**: Consider `{ ok: true; data: T } | { ok: false; error: E }` for expected failures
- **Async/await**: Always wrap with try/catch — unhandled promise rejections crash Node
- **Structured logging**: Use project logger, not `console.log` in production code
- **User-facing errors**: Helpful messages that don't leak stack traces or internals

## Patterns

```typescript
// Good — typed error with context
class ApiError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
    public readonly cause?: Error,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Good — explicit error handling
try {
  const data = await fetchUser(id);
  return { ok: true, data } as const;
} catch (err) {
  logger.error("Failed to fetch user", { userId: id, err });
  return { ok: false, error: "User not found" } as const;
}
```

## Not This

- `catch (e) {}` — empty catch swallows errors silently
- `catch (e) { return null }` — hides failures behind null
- `console.error` as the only error handling — log AND handle
