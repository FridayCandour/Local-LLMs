# Local LLMs

A minimal CLI chat interface for local LLMs using `llama-cpp`. 

This sample talks to **J.O.S.I.E.** (Just One Super Intelligent Entity) — an uncensored AI assistant running on your hardware.

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

## Model Format

Uses ChatML template format:
```


## Notes

- Optimized for old machines like Intel Macs, Raspberry Pis, and other low-end devices (CPU-only, `n_gpu_layers=0`)
- Streaming output for real-time responses 
