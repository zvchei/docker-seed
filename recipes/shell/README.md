# shell

A plain Ubuntu shell with the project mounted at `~/$PROJECT`. It covers both
the `cli` and `shell` examples. A service with no templates and no `cmd` just
inherits Ubuntu's `bash`, which exits right away without a TTY.

## Use

```bash
ds run shell                 # interactive bash
ds shell shell ls -la        # run a single command instead
```

Add templates to `templates` to grow it into a workstation.
