# Search & Navigation

**Never `grep` — always `rtk rg` or `/usr/bin/rg`.** `rtk grep` has GNU grep semantics; don't use it for ripgrep flags.

## Essential rg flags

```bash
rtk rg "pat" src/         # recursive, respects .gitignore
rtk rg -F "exact"         # fixed string
rtk rg -i / -w / -v       # case-insensitive / word / invert
rtk rg -t py -t ts        # by language
rtk rg -g "*.rs" -g "!tests/"   # glob include/exclude
rtk rg --no-ignore        # include .gitignored
rtk rg -l / -c / -C3      # files only / count / context
rtk rg -U "multi\n.line"  # multiline
rtk rg "old" -r "new"     # preview replace
rtk rg --files -g "*.py"  # list files (or use fd)
```

## NOT rg

- Structured data: `jq` / `yq`.
- Find callers / indirect calls: `pyright` / GitNexus (rg misses indirect calls).

## Search before writing

- `rtk rg -l "class.*Error"` before adding an exception class.
- `rtk rg "def.*validate"` before writing a validator.

## Reading strategy

- Targeted line ranges for files >300 lines.
- No 500+ line diff dumps — summarize.
- Read index first (README, `__init__.py`, `mod.rs`), then drill in.
- Map dependencies before editing >3 files.

## Shell hygiene (SHELL-001)

Banned: `| true`, `|| true`, `2>/dev/null`, `set +e`, `--force` to bypass safety. Fix causes, don't silence symptoms.

## Hook-anchored

- `SHELL-001`: capture output, branch on exit status. Don't hide failures.
- `GLOBAL-BUILTIN-SYSTEM-PROTECTION`: don't target `/etc`, `/dev/*`, `/usr/bin/*` as file args.
- `PY-SHELL-001`: don't edit Python via `sed -i`/`tee`/heredocs/redirects. Use Read/Edit/Write.
