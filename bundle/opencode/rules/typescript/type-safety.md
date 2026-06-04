
# TypeScript Type Safety

Enforcer hooks block `any` (TS-TYPE-001), unsafe assertions (TS-TYPE-002), `@ts-ignore`/`@ts-expect-error` (TS-LINT-002), and TODO markers (TS-QUALITY-003).

## Do This

- **`unknown`** instead of `any` — then narrow with type guards
- **Discriminated unions** with `type` or `kind` literal fields
- **`Readonly<T>`** and `as const` by default — mutate only when explicit
- **Strict mode** (`"strict": true` in tsconfig) — no exceptions
- **Zod or Valibot** for runtime API/input validation

## Type Narrowing

```typescript
// Good — inline narrowing
if (typeof value === "string") {
  return value.toUpperCase();
}

// Good — discriminated union
type Result = { ok: true; data: T } | { ok: false; error: string };
if (result.ok) {
  // result.data is available here
}
```

## Not This

- `any` — use `unknown` and narrow
- `as Type` assertions without justification — narrow with guards
- `@ts-ignore` / `@ts-expect-error` — fix the type error
- `// eslint-disable` — fix the lint issue (vibeforcer TS-LINT-001/002)
