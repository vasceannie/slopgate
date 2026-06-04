# Security

## Input validation

- All user data is untrusted — validate with Pydantic (Py) or Zod/Valibot (TS).
- SQL: parameterized queries / ORMs. Check migrations before schema changes.
- Sanitize before DB writes, not just reads.
- Validate file paths (no `../`) and URL inputs (SSRF — allowlist).

## Secrets

- Scan for `sk-`, `ghp_`, `AIza`, private keys before committing.
- Env vars only — never hardcode keys.
- `.env.example` exists before creating/modifying `.env`.
- Never log secrets. Never put them in error messages.

## AuthN/Z

- Hash passwords with `bcrypt`/`argon2`. Never plaintext or reversible.
- Constant-time comparison (`hmac.compare_digest`) for tokens.
- Session tokens in HTTP-only cookies, not localStorage.
- Authorize at every endpoint — don't rely on client-side checks.

## Access

- Least privilege. Local-first: don't send data to external APIs without permission.
- `pathlib` with resolved paths, never string concatenation.

## Hook-anchored

- `GLOBAL-BUILTIN-SENSITIVE-DATA`: don't inspect `.env`, auth, cookie, token, SSH key, or credential files — use templates/examples or ask Trav.
- `GLOBAL-BUILTIN-SYSTEM-PROTECTION`: don't read/write protected system paths.
- If a command used `/dev/null` to suppress errors, remove it and handle the error.
