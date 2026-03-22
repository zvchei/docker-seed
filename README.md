# DockerSeed

DockerSeed is a lightweight, Docker-based environment for secure development in isolated containers. Each service has its own image. The root `docker-compose.yaml` is **generated** when you run `./build.sh`.

## How services get into the tree

There are two ways to prepare container definitions:

- **Templates + `containers.json` (recommended)** - Add or edit entries in `containers.json`, define reusable pieces under `templates/`, then run `./setup.py`. That writes `services/<name>/Dockerfile` and `services/<name>/docker-compose.yaml` and appends new names to `services.list`. Use this for composing services from shared building blocks; one place to merge apt packages, volumes, ports, and Dockerfile fragments.

- **Legacy** - Create or edit `services/<name>/` yourself (Dockerfile, `docker-compose.yaml`, optional `setup.sh`) and list each service in `services.list`. Use this for one-off or highly custom images that you do not want driven by templates.

You can mix both: some directories under `services/` are hand-maintained while others are regenerated from `containers.json` when you run `./setup.py`. Entries in `containers.json` with `"enabled": false` are skipped; they do not overwrite existing `services/<name>/` until you enable them.

## Quick start

1. **Clone** this repository.

2. **Generate services** (required for anything declared in `containers.json` with `"enabled": true`; safe to run if you only use legacy services and all template-driven entries are disabled):

   ```bash
   ./setup.py
   ```

3. **Bake the stack** - runs optional per-service `setup.sh` scripts, regenerates the root `docker-compose.yaml` from `services.list`, walks through `.env`, then optionally runs `docker-compose build`:

   ```bash
   ./build.sh
   ```

4. **Run a service** (pick a name from `services.list`):

   ```bash
   docker-compose up <service_name>
   ```

   For a browser-based editor service, open **http://localhost:8080** (or the port your service maps) once the container is up.

   For day-to-day use, a **Progressive Web App (PWA)** in Chrome is usually nicer than raw tabs: after opening the URL, use **Install** in the address bar, or **Menu → Save and share → Install page as app** (labels vary by Chrome version). You get a dedicated app window without managing a separate kiosk session.

   If you still want a fullscreen, chromeless window (e.g. a dedicated workstation), you can use kiosk mode:

   ```bash
   google-chrome --new --kiosk http://localhost:8080
   ```

## Generating services from templates (`setup.py`)

`setup.py` reads **`containers.json`** and, for each enabled entry, merges the listed **`templates/`** manifests and Dockerfile fragments into `services/<name>/`.

1. Edit **`containers.json`** - list container names, `templates` to merge, and set `"enabled": true` for services you want generated.
2. Run **`./setup.py`** - writes `services/<name>/Dockerfile` and `docker-compose.yaml`, and appends new names to **`services.list`** when missing.
3. Run **`./build.sh`** so per-service setup runs, the root compose file is refreshed, and images are built.

### Template layout

A template is a directory under `templates/` with a manifest and optional Dockerfile fragments:

```
templates/
  my-tool/
    template.json      # manifest
    root.Dockerfile    # optional - runs as root after apt
    user.Dockerfile    # optional - runs as the container user
```

### `template.json`

All fields are optional.

```json
{
  "description": "Human-readable description",
  "apt_packages": ["curl", "git"],
  "volumes": {
    "volume_name": "mount/path/relative/to/home"
  },
  "ports": ["8080:8080"],
  "cmd": ["my-tool", "--serve"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `description` | `string` | What this template provides. |
| `apt_packages` | `string[]` | Packages installed with `apt-get` as root. |
| `volumes` | `{name: path}` | Named volumes, paths relative to `$HOME`. |
| `ports` | `string[]` | Port mappings (`host:container`). |
| `cmd` | `string[]` | Default Docker `CMD`. |

**`root.Dockerfile`** - instructions after the merged `apt-get install`, still as root (system paths, global installs).

**`user.Dockerfile`** - after `USER` / `WORKDIR $HOME` (downloads under `$HOME`, dotfiles, etc.).

### `containers.json`

Each entry combines one or more templates into one service:

```json
[
  {
    "name": "my-container",
    "enabled": true,
    "templates": ["node", "cursor-cli"],
    "cmd": "node"
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | Service name (use `_` not `+` in names). |
| `enabled` | `boolean` | no | If `false`, this entry is skipped (default: `true`). |
| `templates` | `string[]` | yes | Templates to merge; order matters. |
| `cmd` | `string` or `string[]` | no | Overrides container command (see below). |

**`cmd` behavior:**

1. **Omitted** - last template in `templates` that defines `cmd` wins; otherwise no `CMD`.
2. **String** - name of a template whose `template.json` contains the `cmd` to use, e.g. `{ "cmd": "node" }`.
3. **Array** - explicit command, e.g. `{ "cmd": ["node", "server.js"] }`.

## License

This project is licensed under the MIT No Attribution License. See the `LICENSE` file for details.
