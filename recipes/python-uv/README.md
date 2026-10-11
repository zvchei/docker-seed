# python-uv

Two pinned interpreters built with `uv`, side by side. The `python-uv` template
declares `env` as `container_specific`, so each service gets its own venv
volume (`python312_env`, `python314_env`), while the pip/uv download caches are
shared.

## Use

```bash
ds run python312             # interactive bash, Python 3.12 venv active
ds run python314             # interactive bash, Python 3.14 venv active
ds shell python312 ../env/bin/python -m pytest
ds shell python314 ../env/bin/python -m pytest
```

This is handy for testing one project against several Python versions. Add
more services and change `build_args.PYTHON_VERSION` to taste.
