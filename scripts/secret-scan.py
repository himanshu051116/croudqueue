from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv-linux",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
}
FORBIDDEN_FILES = {".env", "backend/.env"}
TEXT_SUFFIXES = {
    "",
    ".cjs",
    ".css",
    ".env.example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "GitHub token": re.compile(r"gh[pousr]_[0-9A-Za-z]{30,}"),
    "OpenAI key": re.compile(r"sk-(?:proj-)?[0-9A-Za-z_-]{20,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Credential assignment": re.compile(
        r"(?i)(?:api[_-]?key|password|passwd|secret|token)\s*[:=]\s*"
        r"[\"'][^\"'\n]{16,}[\"']"
    ),
}
ALLOWED_PLACEHOLDERS = {
    "development-only-change-me-please-32-chars",
    "replace-with-a-long-random-secret",
}


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts)


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"Unable to read {path.relative_to(ROOT)}: {exc}"]
    for line_number, line in enumerate(text.splitlines(), 1):
        if any(placeholder in line for placeholder in ALLOWED_PLACEHOLDERS):
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append(f"{label}: {path.relative_to(ROOT)}:{line_number}")
    return findings


def main() -> int:
    findings: list[str] = []
    for relative in sorted(FORBIDDEN_FILES):
        if (ROOT / relative).exists():
            findings.append(f"Forbidden environment file included: {relative}")

    for path in ROOT.rglob("*"):
        if not path.is_file() or is_excluded(path):
            continue
        suffix = path.suffix.lower()
        if path.name == ".env.example":
            suffix = ".env.example"
        if suffix not in TEXT_SUFFIXES:
            continue
        findings.extend(scan_file(path))

    if findings:
        print("[FAIL] Potential secrets or forbidden files detected:")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("[PASS] No hardcoded secrets or forbidden environment files detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
