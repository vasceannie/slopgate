# Performance Awareness

## Complexity

- **Big O**: Warn if a proposed algorithm has O(n²) or worse complexity
- Prefer `dict`/`set` lookups (O(1)) over `list` scans (O(n)) for membership checks
- Watch for hidden quadratics: nested loops, repeated `.index()`, `x in list` inside a loop

## Memory

- Use **generators/iterators** for large data to avoid loading everything into memory
- `yield` items one at a time instead of building a full list and returning it
- For large files: `for line in file` (streaming) not `file.read()` (all at once)

## Caching

- **`functools.lru_cache`** or `functools.cache` for expensive pure functions
- Consider Redis/memcached for cross-process or distributed caching
- Cache key must be hashable — use `tuple` not `list`

## I/O

- Batch database queries — one query returning N rows beats N queries returning 1
- Use `async` for concurrent I/O (HTTP calls, DB queries) — don't `await` sequentially when requests are independent
- Connection pooling for databases and HTTP clients — don't create/destroy per request

## Lazy Loading

- Don't import or initialize what you don't need yet
- Heavy imports (`pandas`, `torch`) at function scope if only used conditionally
