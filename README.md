# Local LLMs

A minimal CLI chat interface for local LLMs using `llama-cpp`.

This sample talks to JOSIE - JOSIE is a family of uncensored, high-performance language models developed by Gökdeniz Gülmez that blend a friendly, human-like personality with specialized capabilities for natural conversation and complex analytical reasoning.

link to JOSIE [here](https://ollama.com/goekdenizguelmez/JOSIE) created by [Gökdeniz Gülmez - ML Engineer/Researcher](https://github.com/Goekdeniz-Guelmez)

## Explored models:

| Name         | Size  | Context | Input |
| ------------ | ----- | ------- | ----- |
| JOSIE:latest | 2.5GB | 256K    | Text  |

## Requirements

- Python 3.8+
- Local LLM model in GGUF format (compatible with llama_cpp)

## Installation

### 1. Clone and Setup

```bash
git clone this repo
cd "local-llm"
```

### 2. Backend Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install llama_cpp-python (with Metal support for Apple Silicon)
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python
```

### 3. Model Configuration

Download a local LLM model in GGUF format.  
Example using Ollama:

```bash
# Pull a model (saves to ~/.ollama/models/)
ollama pull llama3.2

# Or download GGUF directly from huggingface.
```

### 4. Configuration

Create or edit `config/llm.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  websocket_port: 8765
  debug: false
  cors_origins:
    - "http://localhost:3000"

database:
  path: "./data/chat.db"

llm:
  provider: "llama_cpp"
  model: "~/.ollama/models/blobs/sha256-..." # Path to GGUF file
  system_prompt: "You are a helpful AI assistant."
  max_tokens: 2048
  temperature: 0.7
  top_p: 0.9
  top_k: 40
  context_length: 4096

logging:
  level: "INFO"
  format: "json"
```

### 5. Frontend Setup

The frontend is pure HTML/CSS/JavaScript with no build step required. Simply serve the `frontend/` directory:

```bash
# Using Python's built-in server (development)
cd frontend
python3 -m http.server 3000

# Or serve via the backend (production)
# Backend serves static files automatically
```

## Running the Application

### Development Mode

Start the backend server:

```bash
source .venv/bin/activate
python -m backend.server
```

Start the frontend (separate terminal):

```bash
cd frontend
python3 -m http.server 3000
```

Access the application at `http://localhost:3000`

### Production Mode

```bash
# Build frontend (if applicable)
# Start backend with static file serving
python -m backend.server

# Access at http://localhost:8000
```

### File Attachments

1. Click the attachment icon in the message composer
2. Select a file (PDF, Markdown, JSON, CSV, TXT)
3. File content is extracted and included in context
4. Maximum file size: 50MB per file

### Keyboard Shortcuts

| Shortcut         | Action               |
| ---------------- | -------------------- |
| Ctrl/Cmd + Enter | Send message         |
| Ctrl/Cmd + K     | Open command palette |
| Ctrl/Cmd + 1-9   | Switch to session N  |
| Ctrl/Cmd + /     | Toggle focus mode    |
| Escape           | Close modal/dialog   |

### Configuration Options

#### LLM Parameters

| Parameter      | Description                   | Default |
| -------------- | ----------------------------- | ------- |
| temperature    | Response creativity (0.0-2.0) | 0.7     |
| max_tokens     | Maximum response length       | 2048    |
| top_p          | Nucleus sampling threshold    | 0.9     |
| top_k          | Top-k sampling                | 40      |
| context_length | Conversation history tokens   | 4096    |

#### Context Management

The system maintains conversation history within the context window. When approaching the limit:

- Older messages are summarized
- Key information is preserved
- Token count is displayed in the UI

### Out of Memory

Reduce context length or model parameters:

```yaml
llm:
  context_length: 2048
  n_gpu_layers: 0 # CPU only
```

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## Acknowledgments

- [llama.cpp](https://github.com/ggerganov/llama.cpp) for the excellent local LLM runtime
- [Ollama](https://ollama.com/) for easy model management
- All contributors and users of this project
