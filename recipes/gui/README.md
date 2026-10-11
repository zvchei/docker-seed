# gui

A virtual X display (Xvfb) exported over VNC.

- `gui`: the template's demo (`xmessage 'Hello, world!'`) on `localhost:8900`.
  `x11-utils` is added because it provides `xmessage`.
- `gui_chrome`: a full Chrome desktop on `localhost:8901`. Chrome is started
  through the template's `$ENTRY` hook, and the entrypoint is overridden only to
  give Xvfb a usable 1280×800×24 screen (`xvfb-run`'s default is 640×480×8).

## Use

```bash
ds up gui                    # server: VNC on localhost:8900
ds up gui_chrome             # server: VNC on localhost:8901
vncviewer localhost:8901     # any VNC client, on the host
```

VNC has no password, so the ports are bound to `127.0.0.1`. To run a different
app, set `env_vars.ENTRY` to its command line.
