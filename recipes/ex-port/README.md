# ex-port

Exposes a server that only listens on **localhost** (here a Vite-style
`npm run dev` on port 5173) without changing its configuration.

- `web`: the app. It publishes `127.0.0.1:5173:5173`, but the server inside only
  listens on `localhost`, so Docker's port forwarding can't reach it.
- `web_ex_port`: a tiny socat image that joins `web`'s network namespace
  (`network_mode: service:web`). It listens on `0.0.0.0:5173` and forwards
  to `[::1]:5173`.

## Use

```bash
ds shell web                 # bash: npm create vite@latest . && npm install
ds up web                    # server: npm run dev
ds up web_ex_port            # in another terminal: the proxy → http://localhost:5173
```

`ds up web_ex_port` also starts `web` if it isn't running, because it shares
`web`'s network. Use the two terminals to see the app's own log.

Notes:
- The ports belong to `web`. A service that uses `network_mode: service:…`
  can't publish ports itself.
- The socat proxy listens and connects on the same port, so the app must listen
  on IPv6 loopback (`::1`). Node and .NET do this for `localhost`. A server
  bound to `127.0.0.1:<port>` would clash with the proxy's `0.0.0.0:<port>`.
- `restart: always` brings the proxy back when `web` restarts.
