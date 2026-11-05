"""Central configuration for CodeJudge."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "codejudge.db"
SAMPLES_DIR = ROOT / "samples"
STATIC_DIR = ROOT / "static"

OLLAMA_URL = "http://127.0.0.1:11434"
KEEP_ALIVE = "30m"          # how long Ollama keeps the model in GPU memory
NUM_CTX = 8192              # context window given to the model

# Models offered on the "Select Model" screen.
MODEL_CATALOG = [
    {
        "name": "qwen2.5-coder:7b",
        "label": "Qwen2.5-Coder 7B",
        "size_gb": 4.7,
        "tag": "Recommended",
        "desc": "Best audit quality. Fits fully inside a 6 GB GPU.",
    },
    {
        "name": "qwen2.5-coder:3b",
        "label": "Qwen2.5-Coder 3B",
        "size_gb": 1.9,
        "tag": "Fast",
        "desc": "Roughly 2x faster, slightly less precise.",
    },
    {
        "name": "qwen2.5-coder:1.5b",
        "label": "Qwen2.5-Coder 1.5B",
        "size_gb": 1.0,
        "tag": "Ultra-light",
        "desc": "Runs anywhere. Good for quick demos, weakest judge.",
    },
]

# Weights used to combine the three agent scores into one overall score.
SCORE_WEIGHTS = {"security": 0.5, "quality": 0.25, "performance": 0.25}
