# DockerSeed

DockerSeed is a lightweight, Docker-based environment for secure development in isolated containers. Each service has its own image. The root `docker-compose.yaml` is **generated** when you run `harvest`.

`sow`, `tend`, `harvest`, `configure`, `cleanup`, `transfer`, `backup`, and `restore` operate on the **current working directory**: they read `containers.json` from `$(pwd)`, write generated files under `$(pwd)`, and download assets into `$(pwd)/assets`. `move` accepts an explicit project directory and target. Built-in templates and the shared `common/` base still come from the DockerSeed repository; local `./templates` entries override same-named built-ins.

## How services get into the tree

Add or edit entries in `containers.json`, optionally add project-specific templates under `./templates/`, then run `sow`. That writes `services/<name>/Dockerfile` and `services/<name>/docker-compose.yaml`. Entries with `"enabled": false` are skipped; they do not overwrite existing `services/<name>/` until you enable them. Names beginning with `@` are abstract merge sources and are never generated.

## Quick start

1. **Clone** this repository (or point at an existing clone of the scripts) and put it on your `PATH`, so the scripts can be called by name (each `<name>.py` has a `<name>` symlink):

   ```bash
   export PATH="/path/to/docker-seed:$PATH"
   ```

2. **Scaffold** a project directory (`till` writes `containers.json`, `.env` from `.env.template`, and related files, then runs `configure`; it never overwrites existing files):

   ```bash
   till              # current directory
   till my-project   # create/use ./my-project
   ```

   To start from a ready-made stack instead of the empty default, copy a recipe over the generated file (see [`recipes/`](recipes/README.md)):

   ```bash
   cp /path/to/docker-seed/recipes/jupyter/containers.json my-project/
   ```

3. In your project directory, **generate services**:

   ```bash
   sow
   ```

4. **Manage assets** (optional, only if `sow` wrote an `assets.json`):

   ```bash
   tend
   ```

5. **Bake the stack** (syncs `common/`, regenerates root `docker-compose.yaml`; if `.env` is missing, seeds it from `.env.template` and runs `configure`; can run `docker-compose build`):

   ```bash
   harvest
   ```

   To walk through `.env` again later:

   ```bash
   configure
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

## Generating services from templates (`sow`)

`sow` reads **`containers.json`** from the current directory and, for each enabled entry, merges the listed templates into `services/<name>/`. Template lookup order:

1. `./templates/<name>/` in the current working directory (wins on name clash)
2. `<docker-seed>/templates/<name>/` from the repository that contains the script

`sow` / `harvest` also sync the repo’s `common/` directory into `./common/` when the working directory is not the repo itself, so local builds stay self-contained. The repo ships `.env.template` only; `till` / `harvest` copy it to `./.env` when missing (`harvest` runs `configure` only in that case).

**Workflow:**

1. Edit **`containers.json`** in the project directory - list container names, `templates` to merge, and set `"enabled": true` for services you want generated.
2. Run **`sow`** - writes `services/<name>/Dockerfile` and `docker-compose.yaml` for each enabled entry; writes `assets.json` when needed.
3. **(Optional)** Run **`tend`** - download asset files listed in `assets.json` into `./assets/`.
4. Run **`harvest`** - regenerates the root `docker-compose.yaml`; seeds and configures `.env` only if it was missing; builds images.
5. **(Optional)** Run **`configure`** anytime to review or update `.env` values.

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
| `templates` | `string[]` | no | Templates or service configurations to merge; order matters. Plain names are templates; reference a service as `service:<name>` (abstract `@` services may be written plainly). |
| `extends` | `string` | no | Extend an existing service by name, reusing its image and settings; can be overridden by fields in this entry. |
| `main` | `string` | no | Name of the template whose `cmd` is used as the default (see below). |
| `cmd` | `string[]` | no | Explicit command override, e.g. `["node", "server.js"]`. |
| `entrypoint` | `string[]` | no | Explicit entrypoint override. |
| `ports` | `string[]` | no | Port mappings override (overrides template ports). |
| `init` | `boolean` | no | Run an init process. |
| `restart` | `string` | no | Docker restart policy: `"no"`, `"always"`, `"unless-stopped"`, or `"on-failure"`. |
| `network_mode` | `string` | no | Docker network mode: `"bridge"`, `"host"`, `"none"`, a network name, or `"service:<name>"` to share another service's network namespace. |
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

A plain name always refers to a template, so a service may share a
template's name without breaking other services that use that template, and
adding a new template never makes an existing reference ambiguous. Reference a
non-abstract service with the `service:` prefix:

```json
"templates": ["service:shared", "python"]
```

Abstract (`@`) services may be referenced without the prefix, since template
names cannot start with `@`. A template manifest's `requires` entries continue
to refer only to template directories.

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

Use **`tend`** to download asset files listed in `./assets.json` into `./assets/`. These files can then be copied into containers during build.

Use **`harvest`** to orchestrate setup, compose generation, optional first-time `.env` seeding/configure, and image builds. Use **`configure`** to review or update `.env` anytime.

### Copy directories or files into or out of volumes (`transfer`)

Named volumes persist even when a service is not running. `transfer` copies a host directory or file into a volume (import) or the other way (export) using a one-shot helper container. Direction is inferred from the arguments:

```bash
# Directory as directory — contents of ./dir become volume path dir/
transfer ./dir service:volume:dir

# Directory into directory — trailing / places ./dir inside as dest/dir/
transfer ./dir service:volume:dest/
transfer service:volume:dir ./dest/

# File as file — exact path (rename OK)
transfer ./file.ext service:volume:file.ext
transfer service:volume:file.ext ./path/to/other.ext

# File into directory — trailing / forces dir even if missing
transfer ./file.ext service:volume:dest/
transfer service:volume:file.ext ./dest/
```

The spec is `<service>:<volume>[:<path>]`. `volume` is the Compose key (`root`, `cache`, or a container-specific name such as `chrome_applications`). `<path>` is inside that volume: omitted or `.` for the volume root, a relative path, or an absolute container path under the volume mount.

For files, destinations follow cp/rsync rules: if the destination exists as a directory (or is the volume root on import), the file is placed inside it under the same basename; otherwise the path is the destination file (parent directories are created as needed). A trailing slash forces directory semantics (e.g. `service:volume:dest/` → `dest/<basename>`).

For directories, a destination ending with `/` receives the source directory under its own name (`dest/<basename>/`), creating `dest/` if needed; without the slash, the source's contents become the destination path. Only that nested directory is replaced on overwrite — other entries in `dest/` are left alone.

If the target already exists, the script says so and asks before overwriting (`--force` skips the prompt). Import creates the named volume if it does not exist yet; export fails if the volume or internal path is missing. On import, the transferred files and any directories created for them (including the root of a volume the import creates) are owned by `CONTAINER_USER_ID`.

### Moving a project (`move`)

```bash
move <project> <target> [--force]
```

`<project>` is a path to a directory containing `containers.json`. A `<target>` ending in `/` is an existing directory to move the project into; without a trailing `/`, it is the exact destination path:

```bash
move ./my-project ../
move ./my-project ../newplace/newname
```

The final destination must not already exist; the command never overwrites it. Moving into a directory preserves the project's Docker identity. If the exact destination changes the project name, Docker volumes are copied to the new `<project>_*` prefix, images are retagged (`<project>-*`), and `.env` `COMPOSE_PROJECT_NAME` is updated. These changes are preflight-checked and rolled back on failure. `--force` skips the running-container check and allows reusing an existing Docker resource prefix, but never bypasses the destination-path collision check.

### Archiving and restoring a project (`backup` / `restore`)

`backup` packages a project's source-of-truth files (`containers.json`, `.env`, local `./templates/` overlay, `assets.json`, optionally `secrets/`) together with the live contents of every Docker volume it owns into a single restorable archive:

```bash
backup [output.tar] [--force] [--include-secrets] [--no-secrets]
```

If `output.tar` is omitted, it defaults to `./<project>-backup-<timestamp>.tar`. The archive is written uncompressed so `backup` never sits silently churning through a slow gzip pass; compress it afterwards if you want to save space. Plain `gzip` gives no progress feedback — pipe through `pv` for a live progress bar instead:

```bash
pv backup.tar | gzip > backup.tar.gz
```

If `./secrets/` contains real files (not just placeholders), you're asked whether to include them, unless `--include-secrets`/`--no-secrets` is given. The archive is assembled in a temp staging directory and only moved into place atomically on success, so a failure never leaves a partial backup file behind.

`restore` recreates a project from such an archive, regenerating `services/` and the root `docker-compose.yaml` via `sow`/`harvest`. Both plain `.tar` and gzip-compressed `.tar.gz` archives are accepted:

```bash
restore <archive.tar[.gz]> [directory] [--name NEW_NAME] [--force]
```

`directory` defaults to the current directory (created if it doesn't exist, with confirmation). The project keeps its original name unless `--name` is given. Docker volumes are recreated and their data restored before `sow`/`harvest` run. As with `move`, every step is preflight-checked and ledgered for rollback; if an automatic rollback step fails, a `RESTORE-ROLLBACK-<project>-<timestamp>.txt` file with manual recovery commands is written.

## License

This project is licensed under the MIT No Attribution License. See the `LICENSE` file for details.
