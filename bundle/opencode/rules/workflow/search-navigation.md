# Search & Navigation

## Use `rg` (ripgrep), Not `grep`

ripgrep is faster, respects `.gitignore`, uses sane defaults, and supports modern regex. **Never use `grep` — always `rg`.**

### Essential Patterns

```bash
# Basic search
rg "pattern"                      # recursive, respects .gitignore
rg "pattern" src/                 # search specific directory
rg -F "exact.string"             # fixed string, no regex interpretation
rg -i "pattern"                  # case-insensitive

# Filtering
rg "pattern" -t py               # only Python files
rg "pattern" -t py -t ts         # Python + TypeScript
rg "pattern" -g "*.rs"           # by glob
rg "pattern" -g "!tests/"        # exclude directory
rg "pattern" -g "!*.test.*"      # exclude test files
rg "pattern" --no-ignore         # include .gitignored files

# Output control
rg -l "pattern"                  # list matching files only
rg -c "pattern"                  # count matches per file
rg -C3 "pattern"                 # 3 lines of context
rg -n "pattern"                  # show line numbers (default on)
rg --json "pattern"              # machine-readable output
```

### Advanced Patterns

```bash
# Multiline matching
rg -U "def \w+\(.*\n.*return None"   # span multiple lines

# Replace (preview)
rg "old_name" -r "new_name"          # show replacements (doesn't write)

# Invert match
rg -v "pattern"                      # lines NOT matching

# Word boundary
rg -w "error"                        # match "error" not "errors" or "my_error"

# Logical AND (both patterns in same file)
rg -l "import asyncio" | xargs rg "await"

# Find files by name (use fd, not find)
fd "*.py" src/                       # if fd is installed
rg --files -g "*.py" src/            # ripgrep alternative
```

### When NOT to Use rg

- **Structured data** (JSON, TOML, YAML): use `jq`, `yq`, or language-specific tools
- **AST-level search** (find all callers of a function): use `pyright`, `rg` misses indirect calls
- **Binary files**: rg skips them by default (use `--binary` to override)

## Search Before Writing

Always search for existing patterns before creating new code:
- `rg -l "class.*Error" src/` before adding a new exception class
- `rg "def.*validate" src/` before writing a new validator
- `rg -F "TODO" -t py` to find unfinished work

## Reading Strategy

- **Targeted reading**: Use `read_file` with line ranges for files >300 lines
- **Large diffs**: Summarize logic and show key changes — no 500+ line dumps
- **Progressive disclosure**: Read the index first (README, __init__.py, mod.rs), then drill into specifics
- **Sequential thinking**: Mandatory for tasks involving >3 files — map dependencies before execution

## Shell Hygiene

Don't suppress errors or bypass quality checks in shell commands (vibeforcer SHELL-001 blocks these):

- No `| true` or `|| true` to swallow failures
- No `2>/dev/null` to hide error output
- No `set +e` to disable error checking
- No `--force` flags to bypass safety checks
- If a command fails, fix the cause — don't silence the symptom

## Structured Edit Recovery

- `SHELL-001`: shell quality bypasses are blocked; capture output and branch on exit status instead of hiding failures.
- `GLOBAL-BUILTIN-SYSTEM-PROTECTION`: direct reads/edits of `/etc`, `/dev/*`, `/usr/bin/*`, etc. are protected. Plain `/usr/bin/rg` or `/usr/bin/find` in executable position is not a workaround; run it normally, but do not target protected paths as file arguments.
- `PY-SHELL-001`: do not edit Python source through `sed -i`, `tee`, heredocs, or redirects; use structured read/edit/write tools.
- If a shell command fails, preserve stdout/stderr in the response and fix the cause before retrying.
