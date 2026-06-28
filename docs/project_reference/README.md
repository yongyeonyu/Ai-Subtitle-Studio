# Project Reference

This folder owns stable product, feature, architecture, repository structure,
and domain ownership references.

Canonical files:

- `PRODUCT_README.md`
- `../PROJECT_STATE.md`
- `../FEATURE_REGISTRY.md`
- `../ARCHITECTURE.md`
- `File_structure.txt`
- `CODEMAP.md`
- `LONG_FILE_OWNERSHIP_MAP.md`
- `SUBTITLE_GENERATION_DOMAIN_MAP.md`

Guard tests and checks:

- `tests/test_subtitle_generation_domain_map.py`
- `./venv/bin/python -m pytest -q tests/test_subtitle_generation_domain_map.py`

Rules:

- Update `../ARCHITECTURE.md` when ownership boundaries or repo structure change.
- Update `../FEATURE_REGISTRY.md` when feature owner files or validation entrypoints change.
- Keep `PRODUCT_README.md` as the moved product README; do not recreate root `README.md`.
- Do not infer product behavior from old notes if current source, tests, or release docs disagree.
