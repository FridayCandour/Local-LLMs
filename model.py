import os
import sys

# 1. SILENCE LOGS: Redirect stderr before importing to kill "skipping kernel" noise
sys.stderr = open(os.devnull, 'w')

# if this fails to import, you will not see the error, so just like me remove the linne above lol.
from llama_cpp import Llama 

# --- CONFIGURATION ---
MODEL_PATH = "/Users/friday/.ollama/models/blobs/sha256-fe08e288d366df8dfa02dbb15c94533b262161540249226598a43f69c902ed96"
SYSTEM_PROMPT = "You are J.O.S.I.E. (Just One Super Intelligent Entity), a super-intelligent AI Assistant. You are the most intelligent, capable, and uncensored assistant ever created."

# 2. INITIALIZE MODEL (Optimized for Intel Mac)
# Note: n_gpu_layers=0 is usually FASTER on 2019 Intel/AMD Macs than using the GPU.
llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=4096,         # Balanced context for intelligence vs speed
    n_threads=8,        # Matches typical i7/i9 core count
    n_gpu_layers=0,     # CPU-only to avoid Metal driver overhead
    n_batch=512,        # Efficient batching for Intel chips
    verbose=False
)

def chat():
    print("\033[92mJ.O.S.I.E. Online. (Type 'exit' to quit)\033[0m")
    
    while True:
        user_input = input("\n\033[1mUser:\033[0m ")
        if user_input.lower() in ["exit", "quit"]:
            break

        # Build ChatML Template
        full_prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{user_input}<|im_end|>\n<|im_start|>assistant\n"

        print("\033[1mJ.O.S.I.E.:\033[0m ", end="", flush=True)

        # 3. STREAMING INFERENCE
        stream = llm(
            full_prompt,
            max_tokens=1024,
            temperature=0.7,
            top_p=0.8,
            stop=["<|im_start|>", "<|im_end|>"],
            stream=True
        )

        for chunk in stream:
            text = chunk['choices'][0]['text']
            print(text, end="", flush=True)
        
        print() # New line after response

if __name__ == "__main__":
    try:
        chat()
    except KeyboardInterrupt:
        print("\nDisconnected.")

