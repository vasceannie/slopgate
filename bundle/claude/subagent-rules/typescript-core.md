# TypeScript Standards (subagent digest)
# Source of truth: ~/.claude/rules/typescript/

## Style
- ESM only (`import/export`) — no `require()`
- `async/await` — no raw `.then()` chains
- `camelCase` vars/functions, `PascalCase` types/classes, `UPPER_SNAKE` constants
- Respect `tsconfig.json` path aliases (`@/components/`)
- Detect package manager from lockfile (pnpm/bun/npm) — don't mix
- Prefer `tsx` or `bun` for direct TS execution

## Type Safety
- `unknown` instead of `any` — then narrow with type guards
- Discriminated unions with `type`/`kind` literal fields
- `Readonly<T>` and `as const` by default — mutate only when explicit
- `"strict": true` in tsconfig — no exceptions
- Zod or Valibot for runtime API/input validation
- No `@ts-ignore`/`@ts-expect-error` — fix the type error
- No `// eslint-disable` — fix the lint issue

## Error Handling
- Custom error classes extending `Error` with specific types
- React error boundaries for component failures
- Result types: `{ ok: true; data: T } | { ok: false; error: E }` for expected failures
- Always wrap async/await with try/catch — unhandled rejections crash Node
- No empty `catch {}` — log AND handle

## Not This
- Complex inline JSX styles — use design tokens or Tailwind
- Hardcoded design values — use tokens
- `console.log` in production — remove before completion
