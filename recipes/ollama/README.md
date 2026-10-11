# ollama

- `ollama`: the Ollama server (GPU, Vulkan) on `localhost:11434`. Models persist
  in `~/.ollama`.
- `ollama_chat`: reuses the `ollama` image as a client. It runs
  `ollama run llama3.2` against `http://ollama:11434`.

The server joins the **external** network `ollama_network`, so other DockerSeed
projects can use it too.

## Before you start

Create the network once, before the first start:

```bash
docker network create ollama_network
```

## Use

```bash
ds up ollama                             # server (keep this terminal open)
ds run ollama_chat                       # interactive chat with llama3.2
ds run ollama_chat "why is the sky blue?"   # one-shot prompt (appended to the command)
ds shell ollama_chat pull qwen3          # args follow the `ollama` entrypoint
```

To use this server from another project, add
`"networks": [{"name": "ollama_network", "external": true}]` to a service there
and point it at `http://ollama:11434`. The service name `ollama` is its DNS
name on that network.

`profile: gpu` requests NVIDIA GPUs (needs the NVIDIA container toolkit).
`ollama_chat` inherits that request through `extends`.
