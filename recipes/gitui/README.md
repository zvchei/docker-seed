# gitui

gitui with `git` and `ssh_keys`, so it can also push and pull over SSH (the
plain `gitui` template only pulls in `git`).

## Before you start

Put your SSH key(s) in `secrets/ssh/` before building (rebuild if you add them later).

## Use

```bash
ds run gitui                 # opens gitui on the project repository
ds shell gitui               # bash, e.g. to clone a repository first
```
