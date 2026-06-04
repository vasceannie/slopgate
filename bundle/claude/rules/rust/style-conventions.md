---
globs: **/*.rs, **/Cargo.toml
---

# Rust Style

Hooks block TODO (RS-QUALITY-001), `.unwrap()` (RS-QUALITY-002), magic numbers (RS-QUALITY-003).

## Build

- `cargo check` for fast validation.
- `cargo clippy -- -D warnings` after changes — fix all warnings.
- `cargo fmt` before commits.

## Errors

- `?` with `thiserror` (lib) / `anyhow` (app).
- No `panic!` in lib code.
- `.unwrap()` only in tests — use `.expect("why")` or `?` everywhere else.

```rust
fn load_config(path: &Path) -> Result<Config> {
    let content = fs::read_to_string(path).context("read config")?;
    toml::from_str(&content).context("parse TOML")
}
```

## Types

- `impl Trait` for params, concrete for returns.
- `enum` for finite variants, not stringly-typed.
- `#[must_use]` when the return shouldn't be silently dropped.
- `unsafe` requires `// SAFETY:` comment explaining the invariant.

## Ownership

- Borrow over clone (`&T`, `&mut T`).
- `Cow<'_, str>` when allocation is conditional.
- `Arc`/`Rc` — document why ownership can't be restructured.
- `&str` over `String` when ownership isn't needed.
