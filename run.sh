#!/usr/bin/env bash
# Start CodeJudge: makes sure Ollama is running, then starts the web server.
cd "$(dirname "$0")"
if ! curl -s http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Starting Ollama..."
  nohup ollama serve >/tmp/ollama.log 2>&1 &
  sleep 3
fi
echo "CodeJudge running at http://localhost:8000"
exec .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
