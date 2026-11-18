#!/usr/bin/env bash
# Start CodeJudge.
# Ollama is started only for this session and stopped again on exit (Ctrl+C),
# so the GPU is freed as soon as you close the app.
cd "$(dirname "$0")"
OLLAMA="http://127.0.0.1:11434"
STARTED_OLLAMA=""

if ! curl -s "$OLLAMA/api/version" >/dev/null; then
  echo "Starting Ollama..."
  ollama serve >/tmp/codejudge-ollama.log 2>&1 &
  STARTED_OLLAMA=$!
  for _ in $(seq 1 20); do curl -s "$OLLAMA/api/version" >/dev/null && break; sleep 0.5; done
fi

cleanup() {
  echo
  if [ -n "$STARTED_OLLAMA" ]; then
    kill "$STARTED_OLLAMA" 2>/dev/null
    echo "Ollama stopped - GPU freed."
  else
    # Ollama was already running before us: just unload models from VRAM.
    for m in $(curl -s "$OLLAMA/api/ps" | python3 -c "import json,sys;[print(x['name']) for x in json.load(sys.stdin).get('models',[])]"); do
      curl -s "$OLLAMA/api/generate" -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null
    done
    echo "Models unloaded - GPU freed."
  fi
}
trap cleanup EXIT

echo "CodeJudge running at http://localhost:8000  (Ctrl+C to stop)"
.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
