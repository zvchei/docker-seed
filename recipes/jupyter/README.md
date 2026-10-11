# jupyter

JupyterLab in the shared Python venv, on http://localhost:8888.

## Use

```bash
ds up jupyter                # server; open the …/lab?token=… URL from the log
ds shell jupyter             # bash next to it, e.g. to pip install packages
```

Installed packages persist in the `env` volume, and notebooks live in the
project directory. Jupyter's runtime files and IPython profile are on volumes
because the root filesystem is read-only.
