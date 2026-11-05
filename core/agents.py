"""The judge panel: each agent is a specialised system prompt + a JSON schema.

All agents use the same LLM; what makes them different "agents" is their
role, their rubric and the shape of the verdict they must return.
"""

# ---------------------------------------------------------------- schemas
ISSUE_SCHEMA = {
    "type": "object",
    "properties": {
        "line": {"type": "integer"},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "cwe": {"type": "string"},
    },
    "required": ["line", "severity", "title", "description"],
}

AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 10},
        "summary": {"type": "string"},
        "issues": {"type": "array", "items": ISSUE_SCHEMA},
    },
    "required": ["score", "summary", "issues"],
}

VERIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["true_positive", "false_positive"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "verdict", "reason"],
            },
        }
    },
    "required": ["verdicts"],
}

CHIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "top_risks": {"type": "array", "items": {"type": "string"}},
        "fixed_code": {"type": "string"},
    },
    "required": ["verdict", "top_risks", "fixed_code"],
}

# ---------------------------------------------------------------- prompts
_COMMON = """
You receive Python source code with line numbers in the form "  12 | code".
Rules:
- Report only concrete problems that actually exist in this code. Never invent issues.
- Cite the exact line number from the listing for every issue.
- Keep each description to 1-2 sentences: what is wrong and why it matters.
- If you find nothing in your area, return an empty "issues" list and a high score.
- Stay strictly inside your area of responsibility.
"""

AGENTS = {
    "security": {
        "name": "Security Agent",
        "system": """You are the SECURITY AGENT of an automated code-audit judge panel.
Your area: security vulnerabilities only - SQL/command/code injection, unsafe
deserialization (pickle, yaml.load), hardcoded secrets or credentials, weak
cryptography or hashing (md5/sha1 for passwords), insecure randomness for
tokens, path traversal, SSRF, debug mode enabled, missing input validation on
untrusted data, insecure file permissions. Give a CWE id (e.g. "CWE-89") when
you know it.
Scoring rubric (score = 1..10):
  10 = no security issues
  7-9 = only low-severity issues
  4-6 = at least one medium or high issue
  1-3 = at least one critical issue (remote code execution, injection, leaked credentials)
""" + _COMMON,
    },
    "performance": {
        "name": "Performance Agent",
        "system": """You are the PERFORMANCE AGENT of an automated code-audit judge panel.
Your area: efficiency only - poor algorithmic complexity (e.g. nested loops
that could be a set/dict lookup), repeated expensive work inside loops
(file reads, network or DB calls, regex compilation), string concatenation in
loops, loading whole files into memory unnecessarily, missing caching of
obviously repeated computations, resource leaks (files/connections not closed).
Do not report security or style issues. Use cwe "" for every issue.
Scoring rubric (score = 1..10):
  10 = efficient code
  7-9 = minor inefficiencies
  4-6 = noticeable slowdowns on realistic input sizes
  1-3 = severe problems (quadratic or worse on large data, leaks)
""" + _COMMON,
    },
    "quality": {
        "name": "Code Quality Agent",
        "system": """You are the CODE QUALITY AGENT of an automated code-audit judge panel.
Your area: correctness and maintainability - logic bugs, unhandled edge cases
(None, empty input, division by zero), bare or overly broad except clauses
that hide errors, mutable default arguments, unclear naming, functions doing
too many things, duplicated code, missing error handling around I/O.
Do not report security or performance issues. Use cwe "" for every issue.
Scoring rubric (score = 1..10):
  10 = clean, correct, readable
  7-9 = small readability or robustness issues
  4-6 = likely bugs or hard-to-maintain structure
  1-3 = clearly broken logic
""" + _COMMON,
    },
}

VERIFIER_SYSTEM = """You are the VERIFICATION JUDGE. Static analysis tools (Bandit,
Pylint) produced the warnings listed below for the given Python code. Static
tools are noisy: they flag patterns without understanding context.
For EVERY warning id decide:
  - "true_positive": it is a real problem in this specific code.
  - "false_positive": it is harmless in context (examples: subprocess called with
    a constant argument list and no shell, random used for non-security purposes
    like shuffling, assert inside test code, a "password" variable that is not a secret).
Give a one-sentence reason that refers to the code. Return one verdict per warning id.
"""

CHIEF_SYSTEM = """You are the CHIEF JUDGE of an automated code-audit panel. You receive the
original code and the reports of the Security, Performance and Code Quality
agents plus verified static-analysis findings.
Produce:
  - "verdict": a 2-3 sentence executive summary of the code's overall health,
    written for an engineering manager.
  - "top_risks": the 3 most important problems to fix first (short phrases),
    or an empty list if the code is fine.
  - "fixed_code": the COMPLETE corrected Python file that fixes the security,
    correctness and performance issues while keeping the same behaviour and
    structure. Return plain code only, no markdown fences, no line numbers.
"""
