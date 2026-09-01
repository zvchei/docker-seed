# DockerSeed

DockerSeed is a lightweight, Docker-based environment for secure development in isolated containers. Each service has its own image. The root `docker-compose.yaml` is **generated** when you run `./harvest.py`.

`sow.py`, `tend.py`, `harvest.py`, and `cleanup.py` all operate on the **current working directory**: they read `containers.json` from `$(pwd)`, write generated files under `$(pwd)`, and download assets into `$(pwd)/assets`. Built-in templates and the shared `common/` base still come from the DockerSeed repository; local `./templates` entries override same-named built-ins.

## How services get into the tree

Add or edit entries in `containers.json`, optionally add project-specific templates under `./templates/`, then run `sow.py`. That writes `services/<name>/Dockerfile` and `services/<name>/docker-compose.yaml`. Entries with `"enabled": false` are skipped; they do not overwrite existing `services/<name>/` until you enable them. Names beginning with `@` are abstract merge sources and are never generated.

## Quick start

1. **Clone** this repository (or point at an existing clone of the scripts).

2. **Scaffold** a project directory (`till.py` writes `containers.json`, `.env`, and related files; it never overwrites existing files):

   ```bash
   /path/to/docker-seed/till.py              # current directory
   /path/to/docker-seed/till.py my-project   # create/use ./my-project
   ```

3. In your project directory, **generate services**:

   ```bash
   /path/to/docker-seed/sow.py
   # or, from the repo itself:
   ./sow.py
   ```

4. **Manage assets** (optional, only if `sow.py` wrote an `assets.json`):

   ```bash
   /path/to/docker-seed/tend.py
   ```

5. **Bake the stack** (syncs `common/`, regenerates root `docker-compose.yaml`, walks through `.env`, and can run `docker-compose build`):

   ```bash
   /path/to/docker-seed/harvest.py
   ```

6. **Run a service** (pick a name from `containers.json`):

   ```bash
   docker-compose up <service_name>
   ```

   For a browser-based editor service, open **http://localhost:8080** (or the port your service maps) once the container is up.

   For day-to-day use, a **Progressive Web App (PWA)** in Chrome is usually nicer than raw tabs: after opening the URL, use **Install** in the address bar, or **Menu → Save and share → Install page as app** (labels vary by Chrome version). You get a dedicated app window without managing a separate kiosk session.

   If you still want a fullscreen, chromeless window (e.g. a dedicated workstation), you can use kiosk mode:

   ```bash
   google-chrome --new --kiosk http://localhost:8080
   ```

## Generating services from templates (`sow.py`)

`sow.py` reads **`containers.json`** from the current directory and, for each enabled entry, merges the listed templates into `services/<name>/`. Template lookup order:

1. `./templates/<name>/` in the current working directory (wins on name clash)
2. `<docker-seed>/templates/<name>/` from the repository that contains the script

`sow.py` / `harvest.py` also sync the repo’s `common/` directory into `./common/` when the working directory is not the repo itself, so local builds stay self-contained. `sow.py` also copies the repo's default `.env` into `./.env` when the working directory doesn't already have one.

**Workflow:**

1. Edit **`containers.json`** in the project directory - list container names, `templates` to merge, and set `"enabled": true` for services you want generated.
2. Run **`sow.py`** - writes `services/<name>/Dockerfile` and `docker-compose.yaml` for each enabled entry; writes `assets.json` when needed.
3. **(Optional)** Run **`tend.py`** - download asset files listed in `assets.json` into `./assets/`.
4. Run **`harvest.py`** - regenerates the root `docker-compose.yaml`, walks through `.env`, and optionally builds images.

### Template layout

A template is a directory under `templates/` (repo built-ins and/or local overrides) with a manifest and optional Dockerfile fragments:

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
    "shared_volume_name": "mount/path/relative/to/home",
    "container_volume_name": {
      "path": ".local",
      "container_specific": true
    }
  },
  "ports": ["8080:8080"],
  "cmd": ["my-tool", "--serve"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `description` | `string` | What this template provides. |
| `apt_packages` | `string[]` | Packages installed with `apt-get` as root. |
| `volumes` | `{name: path \| {path, container_specific}}` | Named volumes. Use string form for shared names or object form with `container_specific: true` to prefix with `<container>_` and keep volumes private. Paths are relative to `$HOME`. |
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
| `templates` | `string[]` | no | Templates or service configurations to merge; order matters. Use `template:<name>` or `service:<name>` to resolve an ambiguous name. |
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

### Abstract services and service composition

A name beginning with `@` defines an abstract service. Abstract services are
available as merge sources but never generate a container, image, Dockerfile,
or Compose service:

```json
[
  {
    "name": "@shared",
    "env_vars": {
      "SHARED_SETTING": "true"
    }
  },
  {
    "name": "python",
    "templates": ["@shared", "python"]
  }
]
```

Items in `templates` are merged from left to right, then fields declared
directly on the service are applied last. An item can refer to either a
template directory or another service in `containers.json`.

When both namespaces contain the same name, qualify the reference:

```json
"templates": ["service:shared", "template:python"]
```

An unqualified reference matching the current service's own name remains a
template reference, preserving configurations such as
`{"name": "python", "templates": ["python"]}`. A template manifest's
`requires` entries continue to refer only to template directories.

Use service composition to merge configuration while building a new image.
Use `extends` when the child should reuse an existing service's image.
Abstract (`@`) services cannot use or be targets of `extends`.

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

Use **`tend.py`** to download asset files listed in `./assets.json` into `./assets/`. These files can then be copied into containers during build.

Use **`harvest.py`** to orchestrate setup, compose generation, environment prompts, and optional image builds.

## License

This project is licensed under the MIT No Attribution License. See the `LICENSE` file for details.
