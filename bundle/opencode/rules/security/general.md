# Security

## Input & Validation

- All user data is untrusted — validate with Pydantic (Py), Zod/Valibot (TS)
- SQL: parameterized queries or ORMs only — check migrations before schema changes
- Sanitize before database writes, not just reads
- Validate file paths — prevent directory traversal (`../../../etc/passwd`)
- Validate URL inputs — prevent SSRF (don't fetch arbitrary user-provided URLs without allowlist)

## Secrets

- Scan for `sk-`, `ghp_`, `AIza`, private keys before committing
- Use environment variables for API keys — never hardcode
- Check for `.env.example` before creating/modifying `.env`
- **Never log secrets** — mask or redact sensitive values in log output
- **No secrets in error messages** — user-facing errors should not expose keys, tokens, or internal paths

## Authentication & Authorization

- Hash passwords with `bcrypt` or `argon2` — never store plaintext or reversible encryption
- Use constant-time comparison for tokens and secrets (`hmac.compare_digest`)
- Session tokens: HTTP-only cookies, not localStorage
- Check authorization at every endpoint — don't rely on client-side checks alone

## Access

- Least privilege: scripts use minimum necessary permissions
- Local-first: don't send data to external APIs without permission
- File operations: use `pathlib` with resolved paths, never string concatenation

## Why

Vibeforcer blocks sensitive path access (credentials, SSH keys, env files) and hardcoded paths. This rule teaches the habits that keep secrets out of code in the first place.

## Hook-Anchored Secret and System Protection

- `GLOBAL-BUILTIN-SENSITIVE-DATA`: do not inspect `.env`, auth, cookie, token, SSH key, or provider credential files; use templates/examples or ask Trav.
- `GLOBAL-BUILTIN-SYSTEM-PROTECTION`: do not read or write protected system paths to work around tooling.
- If a command used `/dev/null` only to suppress errors, remove the suppression and handle the error explicitly.
