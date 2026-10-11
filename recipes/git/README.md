# git

A git shell with your identity (`GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` from
`.env`), handy aliases (`co`, `br`, `ci`, `st`, `ll`) and SSH.

## Before you start

Put your SSH key(s) in `secrets/ssh/` **before** building (rebuild if you add
them later). They are copied into the image and loaded into `ssh-agent` by
`.bashrc`. `SSH_KNOWN_HOSTS` in `.env` lists the hosts whose keys are scanned at
build time.

## Use

```bash
ds run git                   # interactive bash with git and ssh-agent
ds shell git git status      # run a single git command
```
