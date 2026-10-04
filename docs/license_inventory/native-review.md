# Native component review

The installed Dear PyGui Windows wheel is 2.3.1. Its .pyd SHA-256 is recorded
in inventory.json; wheel URLs and hashes are in uv.lock. Review uses upstream
tag v2.3.1 and its pinned submodule commits, not floating branch license claims.

| Component | Selected terms | Evidence |
|---|---|---|
| Dear PyGui | MIT | Installed wheel license retained under notices/dearpygui |
| Dear ImGui / embedded ProggyClean font | MIT | [Pinned license](native-notices/imgui-MIT.txt) |
| ImPlot | MIT | [Pinned license](native-notices/implot-MIT.txt) |
| imnodes | MIT | [Pinned license](native-notices/imnodes-MIT.txt) |
| ImGuiFileDialog | MIT | [Pinned license](native-notices/ImGuiFileDialog-MIT.txt) |
| stb_image / stb_image_write | MIT option | [Image](native-notices/stb_image-MIT.txt), [write](native-notices/stb_image_write-MIT.txt) |
| FreeType | FTL option, user approved 2026-10-03 | [FTL](native-notices/FreeType-FTL.txt), [license scope](native-notices/FreeType-LICENSE.txt) |

Portions of this software are copyright © The FreeType Project
(https://freetype.org/). All rights reserved.

Dear PyGui's Windows build enables FreeType and DirectX 11. GLFW/gl3w platform
code is selected for non-Windows builds, not this Windows distribution.

- [Pinned platform configuration](https://github.com/hoffstadt/DearPyGui/blob/v2.3.1/src/mvImGuiConfig_win32.h)
- [Pinned native source list](https://github.com/hoffstadt/DearPyGui/blob/v2.3.1/src/CMakeLists.txt)
- [Pinned submodules](https://github.com/hoffstadt/DearPyGui/blob/v2.3.1/.gitmodules)

Native notice source URLs, source hashes and retained-notice hashes are in
native-notices/sources.json. scripts/collect_native_notices.py is a provisioning
utility; the installed app never downloads notices, code, fonts or updates.

Other installed native distributions (Pydantic Core, MarkupSafe, SQLAlchemy,
mypy and rpds-py) have their wheel license texts and binary hashes retained in
the generated inventory. Ruff/mypy are development tools and are not part of
the application runtime. Python/SQLite have the baseline runtime exceptions.

Release limitation: source-level license evidence and installed wheel notices
are not a vendor-attested complete native build SBOM. Audit the final Nuitka
installer, its compiler/runtime DLLs and any additional codec/font components
before Phase 6 distribution. This document does not assert that an unbuilt
installer has passed its license gate.
