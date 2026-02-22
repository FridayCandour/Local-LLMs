# Local LLMs

A minimal CLI chat interface for local LLMs using `llama-cpp`. 

This sample talks to JOSIE - JOSIE is a family of uncensored, high-performance language models developed by Gökdeniz Gülmez that blend a friendly, human-like personality with specialized capabilities for natural conversation and complex analytical reasoning.

link to JOSIE [here](https://ollama.com/goekdenizguelmez/JOSIE) created by [Gökdeniz Gülmez - ML Engineer/Researcher](https://github.com/Goekdeniz-Guelmez)

## Explored models:

| Name | Size | Context | Input |
|------|------|---------|-------|
| JOSIE:latest | 2.5GB | 256K | Text |

## Requirements

- Python 3.8+
- `llama-cpp-python`
- Local model file (compatible with Ollama's blob format)

## Setup

```bash
# Install dependencies
pip install llama-cpp-python

# Update MODEL_PATH in model.py to point to your local model
```

## Usage

```bash
python3 -m venv .venv
source .venv/bin/activate
source .venv/bin/activate.fish
# install dependencies
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python
# run the model
python model.py
```

Type `exit` or `quit` to close the session.

## Configuration

Edit the constants in `model.py`:

| Variable | Description |
|----------|-------------|
| `MODEL_PATH` | Path to your local GGUF model file |
| `SYSTEM_PROMPT` | Persona and behavior instructions for the assistant |
| `n_ctx` | Context window size (default: 4096) |
| `n_threads` | CPU threads for inference (default: 8) |
 

## Notes

- Optimized for old machines like Intel Macs, Raspberry Pis, and other low-end devices (CPU-only, `n_gpu_layers=0`)
- Streaming output for real-time responses 
