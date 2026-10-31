"""Static analysis layer: runs Bandit (security) and Pylint (bugs/quality).

These tools are fast and deterministic but noisy. Their findings are later
passed to the LLM Verification Judge, which labels each one as a real issue
or a false alarm.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PYLINT_SEVERITY = {"fatal": "high", "error": "high", "warning": "medium", "refactor": "low"}
MAX_FINDINGS = 20


def _run_bandit(path: str) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "bandit", "-f", "json", "-q", path],
        capture_output=True, text=True, timeout=120,
    )
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return []
    return [
        {
            "tool": "Bandit",
            "line": r.get("line_number", 0),
            "rule": r.get("test_id", ""),
            "message": r.get("issue_text", ""),
            "severity": r.get("issue_severity", "LOW").lower(),
            "cwe": f"CWE-{r['issue_cwe']['id']}" if r.get("issue_cwe") else "",
        }
        for r in data.get("results", [])
    ]


def _run_pylint(path: str) -> list[dict]:
    proc = subprocess.run(
        [
            sys.executable, "-m", "pylint", path,
            "--output-format=json", "--score=n",
            # skip pure style chatter and "module not installed" noise
            "--disable=C,R0903,E0401",
        ],
        capture_output=True, text=True, timeout=120,
    )
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [
        {
            "tool": "Pylint",
            "line": m.get("line", 0),
            "rule": m.get("symbol", ""),
            "message": m.get("message", ""),
            "severity": PYLINT_SEVERITY.get(m.get("type", ""), "low"),
            "cwe": "",
        }
        for m in data
    ]


def run_static(code: str) -> list[dict]:
    """Run all static tools on a code string and return a numbered list of findings."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "target.py")
        Path(path).write_text(code)
        findings = _run_bandit(path) + _run_pylint(path)
    findings.sort(key=lambda f: f["line"])
    findings = findings[:MAX_FINDINGS]
    for i, f in enumerate(findings, start=1):
        f["id"] = i
    return findings
