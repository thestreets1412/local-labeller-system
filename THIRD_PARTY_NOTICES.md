# Third-party notices

This development baseline retains the installed dependency license texts below.
The user approved certifi/MPL-2.0, typing_extensions/PSF-2.0, and Dear PyGui's FreeType/FTL exception on 2026-10-03.
NumPy/OpenCV are not installed in this Phase 1 environment.

| Package | Version | Scope | License | Notices |
|---|---|---|---|---|
| alembic | 1.20.0 | runtime | MIT | [notice 1](docs/license_inventory/notices/alembic/licenses/LICENSE) |
| annotated-doc | 0.0.5 | runtime | MIT | [notice 1](docs/license_inventory/notices/annotated-doc/licenses/LICENSE) |
| annotated-types | 0.8.0 | runtime | MIT | [notice 1](docs/license_inventory/notices/annotated-types/licenses/LICENSE) |
| anyio | 4.15.1 | runtime | MIT | [notice 1](docs/license_inventory/notices/anyio/licenses/LICENSE) |
| attrs | 26.1.0 | development | MIT | [notice 1](docs/license_inventory/notices/attrs/licenses/LICENSE) |
| certifi | 2026.7.22 | runtime | MPL-2.0 | [notice 1](docs/license_inventory/notices/certifi/licenses/LICENSE) |
| click | 8.5.0 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/click/licenses/LICENSE.txt) |
| colorama | 0.4.6 | development | BSD-3-Clause | [notice 1](docs/license_inventory/notices/colorama/licenses/LICENSE.txt) |
| dearpygui | 2.3.1 | runtime | MIT | [notice 1](docs/license_inventory/notices/dearpygui/licenses/LICENSE) |
| fastapi | 0.142.2 | runtime | MIT | [notice 1](docs/license_inventory/notices/fastapi/licenses/LICENSE) |
| h11 | 0.16.0 | runtime | MIT | [notice 1](docs/license_inventory/notices/h11/licenses/LICENSE.txt) |
| httpcore | 1.0.9 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/httpcore/licenses/LICENSE.md) |
| httpx | 0.28.1 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/httpx/licenses/LICENSE.md) |
| idna | 3.20 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/idna/licenses/LICENSE.md) |
| iniconfig | 2.3.0 | development | MIT | [notice 1](docs/license_inventory/notices/iniconfig/licenses/LICENSE) |
| jsonschema | 4.26.0 | development | MIT | [notice 1](docs/license_inventory/notices/jsonschema/licenses/COPYING) |
| jsonschema-specifications | 2025.9.1 | development | MIT | [notice 1](docs/license_inventory/notices/jsonschema-specifications/licenses/COPYING) |
| mako | 1.4.3 | runtime | MIT | [notice 1](docs/license_inventory/notices/mako/licenses/LICENSE) |
| markupsafe | 3.0.4 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/markupsafe/licenses/LICENSE.txt) |
| mypy | 1.15.0 | development | MIT | [notice 1](docs/license_inventory/notices/mypy/LICENSE) |
| mypy-extensions | 1.1.0 | development | MIT | [notice 1](docs/license_inventory/notices/mypy-extensions/licenses/LICENSE) |
| opentelemetry-api | 1.45.0 | runtime | Apache-2.0 | [notice 1](docs/license_inventory/notices/opentelemetry-api/licenses/LICENSE) |
| packaging | 26.3 | development | Apache-2.0 OR BSD-2-Clause | [notice 1](docs/license_inventory/notices/packaging/licenses/LICENSE), [notice 2](docs/license_inventory/notices/packaging/licenses/LICENSE.APACHE), [notice 3](docs/license_inventory/notices/packaging/licenses/LICENSE.BSD) |
| pluggy | 1.6.0 | development | MIT | [notice 1](docs/license_inventory/notices/pluggy/licenses/LICENSE) |
| pydantic | 2.13.5 | runtime | MIT | [notice 1](docs/license_inventory/notices/pydantic/licenses/LICENSE) |
| pydantic-core | 2.46.5 | runtime | MIT | [notice 1](docs/license_inventory/notices/pydantic-core/licenses/LICENSE) |
| pygments | 2.21.0 | development | BSD-2-Clause | [notice 1](docs/license_inventory/notices/pygments/licenses/LICENSE) |
| pytest | 8.4.2 | development | MIT | [notice 1](docs/license_inventory/notices/pytest/licenses/LICENSE) |
| referencing | 0.37.0 | development | MIT | [notice 1](docs/license_inventory/notices/referencing/licenses/COPYING) |
| rpds-py | 2026.6.3 | development | MIT | [notice 1](docs/license_inventory/notices/rpds-py/licenses/LICENSE) |
| ruff | 0.16.10 | development | MIT | [notice 1](docs/license_inventory/notices/ruff/licenses/LICENSE) |
| sqlalchemy | 2.1.3 | runtime | MIT | [notice 1](docs/license_inventory/notices/sqlalchemy/licenses/LICENSE) |
| starlette | 1.7.0 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/starlette/licenses/LICENSE.md) |
| typing-extensions | 4.16.0 | runtime | PSF-2.0 | [notice 1](docs/license_inventory/notices/typing-extensions/licenses/LICENSE) |
| typing-inspection | 0.4.4 | runtime | MIT | [notice 1](docs/license_inventory/notices/typing-inspection/licenses/LICENSE) |
| uvicorn | 0.54.0 | runtime | BSD-3-Clause | [notice 1](docs/license_inventory/notices/uvicorn/licenses/LICENSE.md) |

See [native component review](docs/license_inventory/native-review.md) for Dear PyGui and native-wheel evidence.
Runtime uses Windows Imaging Component and the Windows-installed Tahoma font; these OS files are not copied or redistributed.
Python/SQLite retain the runtime exceptions in the specification. Release packaging must include the Python runtime notices and an audit of the final installer contents.
Build frontends/backends are provisioning tools, not bundled runtime; they require their own toolchain inventory before the Phase 6 installer release.
