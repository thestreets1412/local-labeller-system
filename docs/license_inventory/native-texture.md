# Optional VisionLabel native texture wheel

Version 0.1.0; CPython 3.12, Windows x64; Rust MSVC release build.
Exact dependencies and checksums: `native/texture/Cargo.lock`.
Retained upstream notices: `native/texture/THIRD_PARTY_NOTICES.txt`, included in
the native wheel. No additional image codec is bundled; decoding remains OS WIC.

Runtime crates: PyO3 0.27.2, pyo3-ffi 0.27.2, libc 0.2.190,
memoffset 0.9.1, once_cell 1.21.4, unindent 0.2.4. Select MIT for these crates.
Rust runtime components use the toolchain's MIT/Apache-2.0 licensing.

Cargo's build/procedural-macro graph additionally includes autocfg, heck, indoc,
proc-macro2, pyo3-build-config, pyo3-macros, pyo3-macros-backend, quote, rustversion,
syn, target-lexicon and unicode-ident. Those execute during compilation, not at
application runtime. In particular unicode-ident's Unicode-3.0 tables and
target-lexicon's Apache-2.0 WITH LLVM-exception build code are not linked into the
distributed extension. Their notices are retained for build provenance; this is
not approval to add either as an application runtime dependency. Cargo.lock may
also contain platform-conditional crates not compiled for this target.

The compiler and maturin are developer tools, not installed by the native wheel.
The Python dependency inventory remains applicable to the base application.
