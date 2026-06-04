---
globs: **/*.ts, **/*.tsx, **/*.js, **/*.jsx
---

# TypeScript Style

- Detect package manager from lockfile (`pnpm`/`bun`/`npm`); don't mix.
- Direct TS execution via `tsx` or `bun`.
- Monorepo: run commands inside the relevant package only.
- ESM only — no `require()` outside legacy CJS.
- `async/await` only — no raw `.then()` chains.
- Naming: `camelCase` vars/fns, `PascalCase` types/classes, `UPPER_SNAKE` constants.
- Respect `tsconfig.json` path aliases.

## Don't

- Complex inline JSX styles → tokens or Tailwind (STYLE-004).
- Hardcoded colors/spacing → tokens (STYLE-005).
- `console.log` in production code.
