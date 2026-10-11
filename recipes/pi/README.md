# pi

The Pi coding agent with Node.js, git and your SSH keys, so it can commit
and push. Pi state (`~/.pi`) persists on a volume.

## Before you start

Put your SSH key(s) in `secrets/ssh/` before building (rebuild if you add them later).

## Use

```bash
ds run pi                    # start the agent in the project directory
ds run pi -p "summarise the README"   # arguments are appended to `pi`
ds shell pi                  # bash in the same container image
```

Authenticate with `/login` inside pi, or pass a provider key by adding, e.g.,
`"env_vars": {"ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"}` to the service and
the value to `.env`. Pi is installed into the image; rebuild to upgrade.
