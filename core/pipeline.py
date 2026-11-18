"""The audit pipeline: static tools -> 3 specialist agents -> verifier -> chief judge.

`run_audit` is an async generator that yields progress events so the frontend
can show each stage live, and finally yields the complete audit result.
"""
import asyncio
import difflib
import json
import time
from datetime import datetime, timezone

from . import ollama_client as oc
from . import storage
from .agents import (AGENT_SCHEMA, AGENTS, CHIEF_SCHEMA, CHIEF_SYSTEM,
                     VERIFIER_SCHEMA, VERIFIER_SYSTEM)
from .analyzers import run_static
from .config import SCORE_WEIGHTS

SEVERITIES = ["critical", "high", "medium", "low"]
CRITICAL_KEYWORDS = [
    "injection", "cwe-89", "cwe-78", "cwe-94", "cwe-95", "eval(", "exec(", "pickle",
    "cwe-502", "deserializ", "remote code execution", "hardcoded credential",
    "hardcoded secret", "hardcoded password", "hardcoded api key", "hard-coded", "cwe-798",
]


PERF_WORDS = ["loop", "concaten", "complex", "nested", "quadratic", "leak", "close",
               "memory", "cache", "slow", "performance", "efficien", "repeated"]


def _similar(a: str, b: str) -> bool:
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.5


def number_lines(code: str) -> str:
    return "\n".join(f"{i:>4} | {line}" for i, line in enumerate(code.splitlines(), start=1))


def _clean_agent(raw: dict, max_line: int) -> dict:
    """Make the model output safe to use: clamp scores, fix bad fields."""
    score = raw.get("score", 5)
    score = max(1, min(10, int(score))) if isinstance(score, (int, float)) else 5
    issues = []
    for it in raw.get("issues", []) or []:
        if not isinstance(it, dict) or not it.get("title"):
            continue
        line = it.get("line") if isinstance(it.get("line"), int) else 0
        sev = it.get("severity") if it.get("severity") in SEVERITIES else "medium"
        issues.append({
            "line": line if 0 < line <= max_line else 0,
            "severity": sev,
            "title": str(it.get("title", ""))[:160],
            "description": str(it.get("description", ""))[:600],
            "cwe": str(it.get("cwe", "") or ""),
        })
    issues.sort(key=lambda i: SEVERITIES.index(i["severity"]))
    return {"score": score, "summary": str(raw.get("summary", "")), "issues": issues}


def grade_for(score: float) -> str:
    for cutoff, letter in [(9, "A"), (7.5, "B"), (6, "C"), (4, "D")]:
        if score >= cutoff:
            return letter
    return "F"


def side_by_side_diff(old: str, new: str) -> list[dict]:
    """Rows for a two-column diff view: {type, l_no, l, r_no, r}."""
    a, b = old.splitlines(), new.splitlines()
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({"type": "equal", "l_no": i1 + k + 1, "l": a[i1 + k],
                             "r_no": j1 + k + 1, "r": b[j1 + k]})
        else:
            for k in range(max(i2 - i1, j2 - j1)):
                li, rj = i1 + k, j1 + k
                rows.append({
                    "type": tag,
                    "l_no": li + 1 if li < i2 else None, "l": a[li] if li < i2 else None,
                    "r_no": rj + 1 if rj < j2 else None, "r": b[rj] if rj < j2 else None,
                })
    return rows


def _strip_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1] if "\n" in code else ""
        if code.rstrip().endswith("```"):
            code = code.rstrip()[:-3]
    return code.strip("\n") + "\n"


async def run_audit(code: str, filename: str, model: str):
    def step(sid, status, **extra):
        return {"type": "step", "step": sid, "status": status, **extra}

    started = time.time()
    numbered = number_lines(code)
    max_line = len(code.splitlines())

    # 1. Static analysis ---------------------------------------------------
    t = time.time()
    yield step("static", "running")
    findings = await asyncio.to_thread(run_static, code)
    yield step("static", "done", detail=f"{len(findings)} warnings", secs=round(time.time() - t, 1))

    # 2. Specialist agents --------------------------------------------------
    agents = {}
    for key, agent in AGENTS.items():
        t = time.time()
        yield step(key, "running")
        raw = await oc.chat_json(model, agent["system"], f"Code to audit:\n\n{numbered}", AGENT_SCHEMA)
        agents[key] = _clean_agent(raw, max_line)
        yield step(key, "done", detail=f"score {agents[key]['score']}/10 · "
                   f"{len(agents[key]['issues'])} issues", secs=round(time.time() - t, 1))

    # Rule 1 - severity normalisation: well-known exploitable classes are always critical.
    for i in agents["security"]["issues"]:
        text = f"{i['title']} {i['description']} {i['cwe']}".lower()
        if any(k in text for k in CRITICAL_KEYWORDS):
            i["severity"] = "critical"
    # Rule 2 - one owner per line: lines flagged by Security belong to Security only,
    # which removes duplicate / hallucinated findings from the other agents.
    sec_lines = {i["line"] for i in agents["security"]["issues"]}
    for key in ("performance", "quality"):
        agents[key]["issues"] = [i for i in agents[key]["issues"] if i["line"] not in sec_lines]
    # Rule 3 - Performance vs Quality duplicates (same line, similar title): keep one copy,
    # in Performance only if the title is clearly about speed/resources.
    for p in list(agents["performance"]["issues"]):
        for q in list(agents["quality"]["issues"]):
            if p["line"] == q["line"] and _similar(p["title"], q["title"]):
                if any(w in p["title"].lower() for w in PERF_WORDS):
                    agents["quality"]["issues"].remove(q)
                else:
                    agents["performance"]["issues"].remove(p)
                    break

    # 3. Verification judge on static findings ----------------------------
    t = time.time()
    yield step("verify", "running")
    if findings:
        listing = "\n".join(
            f"[{f['id']}] {f['tool']} {f['rule']} line {f['line']}: {f['message']}" for f in findings
        )
        raw = await oc.chat_json(model, VERIFIER_SYSTEM,
                                 f"Code:\n\n{numbered}\n\nWarnings:\n{listing}", VERIFIER_SCHEMA)
        verdicts = {v.get("id"): v for v in raw.get("verdicts", []) if isinstance(v, dict)}
        for f in findings:
            v = verdicts.get(f["id"], {})
            f["verdict"] = v.get("verdict", "unverified")
            f["reason"] = v.get("reason", "The judge did not return a verdict for this warning.")
    confirmed = sum(f.get("verdict") == "true_positive" for f in findings)
    rejected = sum(f.get("verdict") == "false_positive" for f in findings)
    yield step("verify", "done", detail=f"{confirmed} confirmed · {rejected} false alarms",
               secs=round(time.time() - t, 1))

    # 4. Chief judge ----------------------------------------------------------
    t = time.time()
    yield step("chief", "running")
    panel = {
        k: {"score": a["score"], "summary": a["summary"],
            "issues": [f"line {i['line']} [{i['severity']}] {i['title']}" for i in a["issues"]]}
        for k, a in agents.items()
    }
    real_static = [f"line {f['line']}: {f['message']}" for f in findings if f.get("verdict") == "true_positive"]
    raw = await oc.chat_json(
        model, CHIEF_SYSTEM,
        f"Original code:\n\n{code}\n\nAgent reports:\n{json.dumps(panel, indent=2)}\n\n"
        f"Confirmed static findings:\n{json.dumps(real_static, indent=2)}",
        CHIEF_SCHEMA,
    )
    fixed = _strip_fences(str(raw.get("fixed_code", ""))) if raw.get("fixed_code") else ""
    if not any(a["issues"] for a in agents.values()) and confirmed == 0:
        fixed = ""                         # nothing to fix -> don't show a cosmetic rewrite
    yield step("chief", "done", detail="verdict + auto-fix ready", secs=round(time.time() - t, 1))

    # 5. Deterministic scoring ------------------------------------------------
    scores = {k: a["score"] for k, a in agents.items()}
    overall = sum(scores[k] * w for k, w in SCORE_WEIGHTS.items())
    has_critical = any(i["severity"] == "critical" for i in agents["security"]["issues"])
    if has_critical:                      # rule: a critical vuln caps the grade at D
        overall = min(overall, 4.0)
    overall = round(overall, 1)

    all_issues = [dict(i, agent=k) for k, a in agents.items() for i in a["issues"]]
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filename": filename or "snippet.py",
        "model": model,
        "duration_s": round(time.time() - started, 1),
        "code": code,
        "scores": scores,
        "overall": overall,
        "grade": grade_for(overall),
        "critical_cap": has_critical,
        "verdict": str(raw.get("verdict", "")),
        "top_risks": [str(r) for r in raw.get("top_risks", []) or []][:5],
        "agents": agents,
        "static": findings,
        "fixed_code": fixed,
        "diff": side_by_side_diff(code, fixed) if fixed and fixed.strip() != code.strip() else [],
        "stats": {
            "issues_total": len(all_issues),
            "by_severity": {s: sum(i["severity"] == s for i in all_issues) for s in SEVERITIES},
            "static_total": len(findings),
            "static_confirmed": confirmed,
            "static_rejected": rejected,
            "lines": max_line,
        },
    }
    result["id"] = await asyncio.to_thread(storage.save_audit, result)
    yield {"type": "result", "audit": result}
