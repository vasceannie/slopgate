# Common Type Stub Packages

Type stubs for popular libraries not yet typed inline.

---

## Official Stubs (types-*)

Maintained by typeshed. Install with `pip install types-{package}`.

| Library | Stub Package | Notes |
|---------|--------------|-------|
| requests | `types-requests` | HTTP client |
| redis | `types-redis` | Redis client |
| PyYAML | `types-PyYAML` | YAML parser |
| python-dateutil | `types-python-dateutil` | Date utilities |
| Pillow | `types-Pillow` | Image processing |
| beautifulsoup4 | `types-beautifulsoup4` | HTML parsing |
| colorama | `types-colorama` | Terminal colors |
| decorator | `types-decorator` | Decorator utils |
| docutils | `types-docutils` | Doc processing |
| Flask | `types-Flask` | Flask types |
| Jinja2 | `types-Jinja2` | Jinja2 templates (partial) |
| Markdown | `types-Markdown` | Markdown parser |
| openpyxl | `types-openpyxl` | Excel files |
| paramiko | `types-paramiko` | SSH client |
| protobuf | `types-protobuf` | Protocol buffers |
| psutil | `types-psutil` | System utilities |
| psycopg2 | `types-psycopg2` | PostgreSQL |
| pyOpenSSL | `types-pyOpenSSL` | OpenSSL bindings |
| pyserial | `types-pyserial` | Serial ports |
| python-slugify | `types-python-slugify` | Slug generation |
| pytz | `types-pytz` | Timezone handling |
| regex | `types-regex` | Regex library |
| Send2Trash | `types-Send2Trash` | Trash files |
| setuptools | `types-setuptools` | Package setup |
| six | `types-six` | Python 2/3 compat |
| tabulate | `types-tabulate` | Table formatting |
| toml | `types-toml` | TOML parser |
| tqdm | `types-tqdm` | Progress bars |
| ujson | `types-ujson` | Fast JSON |

---

## AWS Stubs (boto3-stubs)

```bash
# Core stubs
pip install boto3-stubs

# With specific services
pip install "boto3-stubs[s3,ec2,dynamodb]"

# All services
pip install "boto3-stubs[all]"
```

---

## Libraries with Inline Types

These have built-in type annotations (no stubs needed):

| Library | Since Version |
|---------|---------------|
| SQLAlchemy | 2.0+ |
| Pydantic | 1.0+ |
| FastAPI | 0.1+ |
| httpx | 0.10+ |
| aiohttp | 3.6+ |
| attrs | 19.1+ |
| click | 8.0+ |
| typer | 0.3+ |
| rich | 10.0+ |
| structlog | 21.1+ |
| pendulum | 2.0+ |
| orjson | 3.0+ |
| pytest | 7.0+ |
| numpy | 1.20+ |
| pandas | 1.3+ (partial) |

---

## Checking Stub Availability

```bash
# Check if types package exists
pip index versions types-packagename 2>/dev/null

# Check alternate naming
pip index versions packagename-stubs 2>/dev/null

# Search PyPI
pip search types-packagename  # Note: may be disabled

# Check typeshed directly
# https://github.com/python/typeshed/tree/main/stubs
```

---

## Creating Inline Stubs

When no stubs exist, create `.pyi` files:

```python
# _stubs/untyped_lib.pyi

def some_function(arg: str) -> int: ...

class SomeClass:
    def method(self, x: int) -> str: ...
    @property
    def value(self) -> float: ...
```

Configure in `pyproject.toml`:

```toml
[tool.pyright]
stubPath = "_stubs"

[tool.mypy]
mypy_path = "_stubs"
```

---

## py.typed Marker

Check if a package is typed:

```python
import importlib.util
import pathlib

def is_typed_package(package_name: str) -> bool:
    """Check if package has py.typed marker."""
    spec = importlib.util.find_spec(package_name)
    if spec is None or spec.origin is None:
        return False
    package_dir = pathlib.Path(spec.origin).parent
    return (package_dir / "py.typed").exists()
```
