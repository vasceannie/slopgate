---
name: codegraph-cli
description: Use when exploring unfamiliar code, tracing call flows, or assessing blast radius before refactors. Triggers on "how does X work", "who calls this", impact analysis, or when grep/Read sweeps are burning tokens. Requires a per-project CodeGraph index.
---

# codegraph-cli

[CodeGraph](https://github.com/colbymchenry/codegraph) is a **local** semantic code-intelligence layer (symbol graph, callers/callees, impact). It exposes an **MCP server** to Claude Code, Cursor, Codex, OpenCode, and other agents. It complements Slopgate (**edit-time guardrails**) and overlaps partially with GitNexus — prefer **CodeGraph MCP tools on the repo you are editing** when `.codegraph/` exists; use **GitNexus** when that index is already maintained for the workspace (see repo `gitnexus-*` skills).

Upstream: https://github.com/colbymchenry/codegraph · Docs: https://colbymchenry.github.io/codegraph/

## Install

```bash
# macOS / Linux (bundled runtime, no Node required)
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh

# Windows (PowerShell)
irm https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.ps1 | iex

# Or npm (any OS with Node)
npm i -g @colbymchenry/codegraph
```

Open a **new terminal** so `codegraph` is on PATH, then wire agents:

```bash
codegraph install                    # interactive; detects installed harnesses
codegraph install --yes              # non-interactive auto-detect
codegraph install --target=cursor,claude,codex,opencode --yes
```

Restart each harness after install. Remove from agents only: `codegraph uninstall` (project indexes under `.codegraph/` stay until `codegraph uninit`).

The bundle does **not** write MCP config files — `codegraph install` does (or merge `bundle/shared/mcp/codegraph.mcp.json` manually).

## Per-project setup

```bash
cd your-repo
codegraph init -i          # create .codegraph/ and build index
# later:
codegraph sync             # incremental update
codegraph status           # health / pending sync
```

Re-index from scratch: `codegraph index --force`.

## MCP tools (prefer over grep archaeology)

| Tool | When |
|---|---|
| `codegraph_explore` | **Default** — "how does X work", flows, survey an area (verbatim source + relationship map) |
| `codegraph_search` | Find symbols by name |
| `codegraph_callers` / `codegraph_callees` | Call graph direction |
| `codegraph_impact` | Blast radius before changing a symbol |
| `codegraph_node` | One symbol's details + source |
| `codegraph_files` | Indexed file tree (faster than blind glob) |
| `codegraph_status` | Stale/pending files, index stats |

If a response shows a **pending sync** banner for a file you just edited, `Read` that file for live content, then continue.

## CLI (without MCP)

```bash
codegraph query "UserService"
codegraph callers 'MyClass.method'
codegraph callees 'MyClass.method'
codegraph impact 'MyClass.method'
git diff --name-only | codegraph affected --stdin --quiet   # tests to run
```

## Slopgate + CodeGraph + RTK

| Layer | Role |
|---|---|
| **Slopgate** | Hook/lint enforcement (`slopgate install`, `slopgate lint check`) |
| **CodeGraph** | Structural exploration via MCP (`codegraph install` + `codegraph init -i`) |
| **RTK** | Compact shell output (`rtk init`; see `rtk-cli` skill) |

Install order is flexible; restart harnesses after each MCP/hook installer. Slopgate hook wiring stays **`slopgate install …` only**.

## Staleness

The MCP server watches source files (debounced). `codegraph_status` reports pending files. Edits made while the server was offline are reconciled on the next MCP connection.

## When not to use

- Repo has no index and you cannot run `codegraph init -i` (use `sgt search` / GitNexus / targeted `rtk rg` instead).
- You need **full file text** for a file still pending sync — read it directly.
- Replacing Slopgate quality gates — CodeGraph does not lint or block bad edits.
