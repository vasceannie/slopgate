# Performance Awareness

- **Complexity:** flag O(n²)+. `dict`/`set` lookups (O(1)) over `list` scans. Watch nested loops and `x in list` inside a loop.
- **Memory:** generators/streaming for large data. `for line in file`, not `file.read()`.
- **Caching:** `functools.lru_cache`/`cache` for pure functions. Redis/memcached for cross-process. Hashable keys (`tuple`, not `list`).
- **I/O:** batch DB queries. Concurrent `async` for independent requests. Pool connections.
- **Lazy:** heavy imports (`pandas`, `torch`) at function scope when conditional.
