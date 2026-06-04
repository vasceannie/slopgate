# Atomic Edits

The post-tool-use hook auto-formats after each edit. This creates a timing hazard.

## IMPORTANT: Batch Imports With Usage

Adding an import in one edit and its usage in another → formatter deletes the "unused" import before the second edit runs.

- **Always batch imports + usage in the same edit call**
- Use `edit_file` with `// ... existing code ...` to batch them
- With `str_replace`, use **parallel tool calls** for import + code changes in the same file

## Editor Preference

- Prefer `edit_file` over `str_replace` or full file writes
- `edit_file` works with partial snippets and is less error-prone
