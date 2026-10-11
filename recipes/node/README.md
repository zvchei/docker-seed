# node

- `node`: Node.js v22 REPL (interactive).
- `node_app`: reuses the `node` image (`extends`) to run `npm start` from the
  project root, published on http://localhost:10080. `PORT=8080` and
  `HOST=0.0.0.0` are set so typical servers listen where the port is mapped.

## Use

```bash
ds run node                  # Node.js REPL
ds shell node                # bash: npm init, npm install …
ds up node_app               # server: npm start → http://localhost:10080
ds up node_app -- --watch    # extra args are appended: npm start -- --watch
```

`~/.npm` and `~/.node` are volumes, so the npm cache and REPL history persist.
