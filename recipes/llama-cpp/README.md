# llama-cpp

An **offline** llama.cpp server. The model server sits on an `internal` network
(`llama_local`) with no internet access and no direct host access. The other
services handle the jobs it can't do itself:

| Service | Networks | Role |
|---|---|---|
| `huggingface` | default (internet) | One-shot download of a GGUF into the shared `models` volume |
| `llama_cpp` | `llama_local` (internal) | CUDA llama.cpp server on `:8090`, serving `~/models` |
| `llama_gateway` | `llama_local` + default | socat (`ex_port` template) that forwards `localhost:8090` to `llama_cpp:8090` |
| `pi_local` | `llama_local` (internal) | Pi coding agent that can reach only the local model |

## Before you start

Add `HF_TOKEN=` to `.env` (a token is needed only for gated models).

## Use

```bash
ds run huggingface           # once: downloads qwen2.5-1.5b-instruct-q4_k_m.gguf
ds up llama_cpp              # model server (keep this terminal open)
ds up llama_gateway          # another terminal: web UI / OpenAI API on http://localhost:8090
ds run pi_local              # offline coding agent
```

To use another model, download it into the `models` volume:

```bash
ds shell huggingface ../env/bin/hf download <repo> <file>.gguf --local-dir ../models
```

Point `pi_local` at the server with a custom provider in `~/.pi/agent/models.json`
(base URL `http://llama_cpp:8090/v1`, OpenAI-compatible API; see the pi docs for
the exact schema). Pi itself is installed at build time, which does have network
access.

`llama_cpp` uses `profile: gpu` because the binaries are CUDA builds.
