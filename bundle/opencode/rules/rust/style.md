
# Rust Style & Conventions

Enforcer hooks block TODO markers (RS-QUALITY-001), `.unwrap()` (RS-QUALITY-002), and magic numbers (RS-QUALITY-003).

## Build & Lint

- `cargo check` for fast validation, `cargo build` for full compile
- `cargo clippy -- -D warnings` after changes — fix all warnings
- `cargo fmt` before commits

## Error Handling

- Use `?` with `thiserror` for library errors, `anyhow` for app errors
- Never `panic!` in library code — reserve for truly unrecoverable states
- `.unwrap()` only in tests — use `.expect("context about why this shouldn't fail")` or `?` everywhere else

```rust
// Good — propagate with context
fn load_config(path: &Path) -> Result<Config> {
    let content = fs::read_to_string(path)
        .context("failed to read config file")?;
    let config: Config = toml::from_str(&content)
        .context("failed to parse config TOML")?;
    Ok(config)
}

// Bad
fn load_config(path: &Path) -> Config {
    let content = fs::read_to_string(path).unwrap();  // panics
    toml::from_str(&content).unwrap()                  // panics
}
```

## Types & Patterns

- Prefer `impl Trait` for function params, concrete types for return values
- Use `enum` for state machines and finite variants — not stringly-typed
- `#[must_use]` on functions whose return value shouldn't be silently dropped
- `unsafe` only with explicit justification and a `// SAFETY:` comment explaining the invariant

## Ownership

- Prefer borrowing (`&T`, `&mut T`) over cloning
- Use `Cow<'_, str>` when a function might or might not need to allocate
- `Arc`/`Rc` for shared ownership — document why ownership can't be restructured

## Not This

- `.unwrap()` in non-test code — use `?` or `.expect("why")`
- TODO/FIXME markers — fix it now or file an issue
- Magic numbers — name constants with `const`
- `String` where `&str` suffices — borrow when you don't need ownership
