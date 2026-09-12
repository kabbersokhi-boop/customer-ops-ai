import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
TEXT_SUFFIXES = {
    ".html",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
PATTERNS = {
    "JWT-like token": re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),
    "Airtable PAT": re.compile(r"\bpat[A-Za-z0-9]{12,}\.[A-Za-z0-9]{30,}\b"),
    "NVIDIA API key": re.compile(r"\bnvapi-[A-Za-z0-9_-]{24,}\b"),
    "n8n API token": re.compile(r"\bn8n_api_[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def candidate_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.name == ".env.example" or path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
    return files


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in candidate_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append((str(path.relative_to(ROOT)), line_number, label))
    if findings:
        print("Potential secrets detected (values suppressed):", file=sys.stderr)
        for path, line_number, label in findings:
            print(f"- {path}:{line_number}: {label}", file=sys.stderr)
        return 1
    print(f"Secret scan passed across {len(candidate_files())} text files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
