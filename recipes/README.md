# Recipes

Each sub-directory holds a ready-to-use `containers.json` for a complete, working
project, plus a `README.md` with that recipe's extra steps (under
**Before you start**) and how to use its services.

## Setting up a recipe

Replace `<recipe>` with a sub-directory name, e.g. `jupyter`:

```bash
till my-project
cp recipes/<recipe>/containers.json my-project/
cd my-project
sow
tend      # only if sow wrote assets.json
harvest   # answer Y to build the images
```

`till` writes a default `containers.json`; the `cp` replaces it with the
recipe. Do the recipe's **Before you start** steps before `harvest` builds
the images.

## Running services

The recipe READMEs use `ds` (`ds` from docker-seed, or the `ds` shell
function from `ds-completion.bash`), run from inside the project directory:

```bash
ds up <service> [args…]      # servers: start in the foreground
ds run <service> [args…]     # interactive services, e.g. shells and agents
ds shell <service> [cmd…]    # a one-off command, or bash, in a new container
ds list                      # enabled services in this project
```

Extra `args` are appended to the service's own command. `ds shell` replaces
the command but keeps the entrypoint.
