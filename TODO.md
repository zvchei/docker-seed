# TODO

- [ ] **Decommission legacy services** - Migrate every hand-maintained `services/<name>/` definition into `templates/` plus `containers.json` as a future single source of truth.

- [ ] **Consider YAML for configuration** - Evaluate replacing JSON config files (e.g. `containers.json`, template manifests) with YAML for readability, comments, and multi-line strings.

- [ ] **Convert shell scripts to Python** - Move logic currently in `build.sh` (and any other shell entrypoints) into Python alongside `seed.py` for consistent error handling, easier testing, and multiplatform support.

- [ ] **Add a way to change base compose service** - The seed.py generation currently assumes a `base` service in the root `docker-compose.yaml` that all generated services extend. The legacy services allow for choosing the `gpu` base for CUDA support.