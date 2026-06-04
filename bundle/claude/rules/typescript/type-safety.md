---
globs: **/*.ts, **/*.tsx
---

# TypeScript Type Safety

Hooks block `any` (TS-TYPE-001), unsafe assertions (TS-TYPE-002), `@ts-ignore`/`@ts-expect-error` (TS-LINT-002), TODO (TS-QUALITY-003).

- `unknown` instead of `any`, then narrow.
- Discriminated unions with `kind` literal fields.
- `Readonly<T>` / `as const` by default.
- `"strict": true` always.
- Zod or Valibot for runtime input validation.

```typescript
type Result<T> = { ok: true; data: T } | { ok: false; error: string };

if (typeof value === "string") return value.toUpperCase();
```

## Don't

- `any` → `unknown` + narrow.
- `as Type` without justification → guards.
- `@ts-ignore` / `// eslint-disable` — fix the root cause.
