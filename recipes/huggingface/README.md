# huggingface

Hugging Face Hub CLI (`hf`) in a Python venv. Models, datasets and the login
token are kept on the `huggingface_cache` volume. The `llama-cpp` template
shares that volume, so models downloaded here are visible to it when the
services live in the same project.

## Before you start

Add `HF_TOKEN=` to `.env`. Leave it empty for public models, or set it for gated
ones (or run `hf auth login` inside the container).

## Use

```bash
ds run huggingface                                        # interactive bash, venv active
ds shell huggingface ../env/bin/hf download Qwen/Qwen2.5-0.5B-Instruct
```
