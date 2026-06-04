
# TypeScript/JS Style & Conventions

## Environment

- **Package manager**: Detect `pnpm`, `bun`, or `npm` from lockfile — don't mix
- **Runtime**: Prefer `tsx` or `bun` for direct TS execution
- **Monorepo**: If in a Turbo/Nx workspace, only run commands within the relevant package dir

## Code Style

- **Imports**: ESM only (`import/export`) — no `require()` unless legacy CJS
- **Async**: `async/await` only — no raw `.then()` chains
- **Naming**: `camelCase` vars/functions, `PascalCase` types/classes, `UPPER_SNAKE` constants
- **Path aliases**: Respect `tsconfig.json` paths (e.g., `@/components/`)

## Not This

- Complex inline styles in JSX — use design tokens or Tailwind (vibeforcer STYLE-004)
- Hardcoded design values (colors, spacing) — use tokens (vibeforcer STYLE-005)
- `console.log` for production logging — remove before completion
