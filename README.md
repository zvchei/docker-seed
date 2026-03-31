# DockerSeed

DockerSeed is a lightweight, Docker-based environment for secure development in isolated containers. Each service has its own image. The root `docker-compose.yaml` is **generated** when you run `./harvest.sh`.

## How services get into the tree

Add or edit entries in `containers.json`, define reusable pieces under `templates/`, then run `./seed.py`. That writes `services/<name>/Dockerfile` and `services/<name>/docker-compose.yaml`. Entries with `"enabled": false` are skipped; they do not overwrite existing `services/<name>/` until you enable them.

## Quick start

1. **Clone** this repository.

2. **Generate services** (required for anything declared in `containers.json` with `"enabled": true`; safe to run if you only use legacy services and all template-driven entries are disabled):

   ```bash
   ./seed.py
   ```

3. **Manage assets** (optional, only if you've defined assets in `assets.json`):

   ```bash
   ./grow.py
   ```

4. **Bake the stack** (regenerates root `docker-compose.yaml`, walks through `.env`, and can run `docker-compose build`):

   ```bash
   ./harvest.sh
   ```

5. **Run a service** (pick a name from `containers.json`):

   ```bash
   docker-compose up <service_name>
   ```

   For a browser-based editor service, open **http://localhost:8080** (or the port your service maps) once the container is up.

   For day-to-day use, a **Progressive Web App (PWA)** in Chrome is usually nicer than raw tabs: after opening the URL, use **Install** in the address bar, or **Menu → Save and share → Install page as app** (labels vary by Chrome version). You get a dedicated app window without managing a separate kiosk session.

   If you still want a fullscreen, chromeless window (e.g. a dedicated workstation), you can use kiosk mode:

   ```bash
   google-chrome --new --kiosk http://localhost:8080
   ```

## Generating services from templates (`seed.py`)

`seed.py` reads **`containers.json`** and, for each enabled entry, merges the listed **`templates/`** manifests and Dockerfile fragments into `services/<name>/.`

**Workflow:**

1. Edit **`containers.json`** - list container names, `templates` to merge, and set `"enabled": true` for services you want generated.
2. Run **`./seed.py`** - writes `services/<name>/Dockerfile` and `docker-compose.yaml` for each enabled entry.
3. **(Optional)** Run **`./grow.py`** - download asset files listed in `assets.json` into the `assets/` directory.
4. Run **`./harvest.sh`** - runs optional per-service `setup.sh` scripts (if present), regenerates the root `docker-compose.yaml`, walks through `.env`, and optionally builds images.

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
| `entrypoint` | `string[]` | Docker `ENTRYPOINT`. |
| `init` | `boolean` | Run an init process inside the container. |
| `interactive` | `boolean` | Enable interactive mode with pseudo-TTY. |
| `env_vars` | `{name: value}` | Environment variables for the container. |
| `build_args` | `{name: value}` | Build-time arguments. |
| `contexts` | `{name: path}` | Additional build contexts. |
| `assets` | `boolean` | Include assets directory in build context. |

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
    "main": "node",
    "cmd": ["node", "server.js"]
  }
]
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | Service name (use `_` not `+` in names). |
| `enabled` | `boolean` | no | If `false`, this entry is skipped (default: `true`). |
| `templates` | `string[]` | yes | Templates to merge; order matters. |
| `extends` | `string` | no | Extend an existing service by name, reusing its image and settings; can be overridden by fields in this entry. |
| `main` | `string` | no | Name of the template whose `cmd` is used as the default (see below). |
| `cmd` | `string[]` | no | Explicit command override, e.g. `["node", "server.js"]`. |
| `entrypoint` | `string[]` | no | Explicit entrypoint override. |
| `ports` | `string[]` | no | Port mappings override (overrides template ports). |
| `init` | `boolean` | no | Run an init process. |
| `restart` | `string` | no | Docker restart policy: `"no"`, `"always"`, `"unless-stopped"`, or `"on-failure"`. |
| `network_mode` | `string` | no | Docker network mode: `"bridge"`, `"host"`, `"none"`, or a network name. |
| `workdir` | `string` | no | Working directory for the container. |
| `interactive` | `boolean` | no | Enable interactive mode and allocate a pseudo-TTY (for shell-like containers). |
| `env_vars` | `{name: value}` | no | Environment variables. |
| `networks` | `array` | no | List of networks to connect to. |
| `profile` | `string` | no | Base service profile (e.g. `"gpu"`). |

**Command resolution order:**

1. **`cmd` omitted, `main` omitted** - last template in `templates` that defines `cmd` wins; otherwise no `CMD`.
2. **`main` set** - the named template's `cmd` is used as the default, e.g. `{ "main": "node" }`.
3. **`cmd` set** - explicit array always overrides any default, e.g. `{ "cmd": ["node", "server.js"] }`.

## Advanced features

### Service extension

Reuse an existing service's image and settings by extending it:

```json
{
  "name": "my-extended-service",
  "extends": "my-container"
}
```

This copies the image, volumes, ports, and other settings from `my-container`. You can override specific fields in the extending entry.

### Asset management

Use **`grow.py`** to download asset files listed in `assets.json` into the `assets/` directory. These files can then be copied into containers during build. Run:

```bash
./grow.py --help
```

Use **`harvest.sh`** to orchestrate setup, compose generation, environment prompts, and optional image builds.

## License

This project is licensed under the MIT No Attribution License. See the `LICENSE` file for details.
