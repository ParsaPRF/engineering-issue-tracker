"""Check that every text file in the repository is valid UTF-8.

Why this exists: on Windows, shell tools such as PowerShell's ``Add-Content``/``Set-Content`` write
the system code page by default. Appending an em dash that way inserts a single ``0x97`` byte, which
is *invalid UTF-8* — the file then breaks editors, diff tools and anything that reads it as UTF-8
(this actually happened to a documentation file during delivery).

Usage (from anywhere):

    python backend/tools/check_encoding.py .        # or pass an absolute repository root

Exit code 0 when clean, 1 when one or more files are not valid UTF-8. It is a maintenance tool, not
part of the application: it imports nothing from Django and is not collected by pytest.
"""

from __future__ import annotations

import pathlib
import sys

SKIP_DIRECTORIES = {
    ".git",
    "node_modules",
    "dist",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "staticfiles",
    "media",
}
BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".sqlite3",
    ".zip",
    ".gz",
}


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1] if len(argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    offenders: list[str] = []
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or SKIP_DIRECTORIES & set(path.parts):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        checked += 1
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            offenders.append(str(path.relative_to(root)))

    print(f"checked {checked} text files under {root}")
    if offenders:
        print("not valid UTF-8:")
        for offender in offenders:
            print(f"  {offender}")
        return 1
    print("all text files are valid UTF-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))