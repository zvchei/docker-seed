# vscode-copilot

One image, two services:

- `code`: VS Code `serve-web` on http://localhost:8080 with git, SSH and the
  Copilot CLI available in its terminal.
- `copilot`: the same image (`extends: code`), started straight into the
  Copilot CLI. Its ports are reset so it can run next to `code`.

## Before you start

Put your SSH key(s) in `secrets/ssh/` before building (rebuild if you add them later).

## Use

```bash
ds up code                   # server: open http://localhost:8080
ds run copilot               # interactive Copilot CLI (another terminal)
```

VS Code runs `--without-connection-token`, so the port is bound to `127.0.0.1`
only.
