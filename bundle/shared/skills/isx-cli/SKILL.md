---
name: isx-cli
description: Use when the user asks to index repositories, run semantic code search, switch embedding models, or rebuild islands indexes. Triggers on requests like "search this repo semantically", "index this repo with islands", "switch embedding model", or "reindex after changing models".
---

# isx-cli

Semantic code search via slopgate's `search` subcommand group (absorbed from the former standalone `isx` CLI). All commands are now under `sgt search`, `slopgate search`, or the deprecated `isx` alias.

## Commands

| Command | What it does |
|---|---|
| `sgt search init` | First-time setup (config, indexes dir, skill scaffolds) |
| `sgt search doctor` | Check runtime health (binary, config, model connectivity) |
| `sgt search list` | Show known indexes |
| `sgt search add <repo-url>` | Index a repository |
| `sgt search query "text"` / `sgt search "text"` | Semantic search |
| `sgt search models` | List available embedding models |
| `sgt search use <model>` | Switch active embedding model |
| `sgt search reindex <repo-or-index>` | Rebuild index (required after changing to a model with different embedding dimensions) |
| `sgt search sync` | Pull latest from remotes and refresh indexes |
| `sgt search remove <index>` | Remove an index |
| `sgt search completions <bash\|zsh>` | Print shell completion script |

## Workflow

1. Run `sgt search doctor` if the runtime may not be configured yet.
2. Use `sgt search list` to see known indexes.
3. Use `sgt search add <repo-url>` to index a repository.
4. Use `sgt search query "query"` for semantic search.
5. Use `sgt search models` and `sgt search use <model>` when changing embedding routes.
6. After changing to a model with a different embedding dimension, run `sgt search reindex <repo-or-index>` before searching again.

## Notes

- All `isx` subcommands work identically under `sgt search` — same config at `~/.config/isx/config.json`, same indexes at `~/.local/share/isx/indexes/`.
- `sgt search` wraps the `islands-ollama` binary and injects the configured OpenAI-compatible base URL and API key.
- `sgt search reindex` is the safe recovery path after model changes.
- Shell completion: `sgt search completions zsh` (or bash).
