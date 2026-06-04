# Atomic Edits

The post-tool-use hook auto-formats after each edit. Adding an import in one edit and its usage in another → formatter deletes the "unused" import before the second edit runs.

- **Batch imports + usage in the same edit.**
- Prefer `edit_file` (partial snippets, less error-prone) over `str_replace` or full rewrites.
- With `str_replace`, use parallel tool calls for import + usage in one file.
