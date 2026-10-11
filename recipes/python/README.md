# python

The distribution's Python 3 with a virtualenv at `~/env`, kept on the `env`
volume and activated in `.bashrc`. `pip install` results persist between runs.

## Use

```bash
ds run python                       # interactive bash with the venv active
ds shell python ../env/bin/python script.py
```

`PIP_INDEX_URL` / `PIP_TRUSTED_HOST` are passed through from `.env`. Add them
there for a private index, or leave them unset (compose warns, pip uses PyPI).

If you add `jupyter`, `huggingface` or `vscode` to the same project, they share
the `env` volume, and the first service to mount it fills it. Make the venv
private to a service with
`"volumes": {"env": {"path": "env", "container_specific": true}}`.
