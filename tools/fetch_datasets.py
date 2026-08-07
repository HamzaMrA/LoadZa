"""Download the OR-Library container loading benchmark files.

    python -m tools.fetch_datasets            # download anything missing
    python -m tools.fetch_datasets --verify   # re-check what is already there

The datasets are not committed. They belong to OR-Library, and a repository is
not the right place to redistribute someone else's research data. What *is*
committed is ``bench/datasets/CHECKSUMS.txt``: run this once and every later
benchmark run is reproducible against exactly the files the published numbers
came from. After the first fetch nothing here needs a network again.

Sets, as OR-Library packages them:

    thpack1..7   Bischoff & Ratcliff BR1..BR7, 100 instances each, box types
                 3, 5, 8, 10, 12, 15, 20 -- weakly to strongly heterogeneous
    thpack8      Loh & Thanapalan, 15 instances, the older small benchmark
    thpack9      47 small instances, containers only a few units across --
                 fast regression material rather than a quality benchmark

thpack10 and thpack11 exist on the server but are byte-identical copies of
thpack1, so they are not fetched. The Davies & Bischoff extension (BR8..BR15)
is not part of OR-Library.
"""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

BASE_URL = "https://people.brunel.ac.uk/~mastjjb/jeb/orlib/files"
DATASET_DIR = Path("bench/datasets")
CHECKSUM_FILE = DATASET_DIR / "CHECKSUMS.txt"
FILES = tuple(f"thpack{n}.txt" for n in range(1, 10))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def read_checksums() -> dict[str, str]:
    if not CHECKSUM_FILE.exists():
        return {}
    entries = {}
    for line in CHECKSUM_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(maxsplit=1)
        entries[name] = digest
    return entries


def write_checksums(entries: dict[str, str]) -> None:
    lines = [
        "# sha256 of the OR-Library container loading files, as fetched.",
        "# Regenerate with: python -m tools.fetch_datasets",
    ]
    lines += [f"{entries[name]}  {name}" for name in sorted(entries)]
    CHECKSUM_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fetch(name: str, force: bool = False) -> Path:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    target = DATASET_DIR / name
    if target.exists() and not force:
        return target
    url = f"{BASE_URL}/{name}"
    with urllib.request.urlopen(url, timeout=60) as response:
        target.write_bytes(response.read())
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch CLP benchmark datasets")
    parser.add_argument("--verify", action="store_true",
                        help="check existing files against CHECKSUMS.txt")
    parser.add_argument("--force", action="store_true", help="re-download everything")
    args = parser.parse_args()

    known = read_checksums()

    if args.verify:
        if not known:
            print("no CHECKSUMS.txt yet; run without --verify first")
            return 1
        bad = 0
        for name, expected in known.items():
            path = DATASET_DIR / name
            if not path.exists():
                print(f"MISSING  {name}")
                bad += 1
            elif sha256(path) != expected:
                print(f"CHANGED  {name}")
                bad += 1
            else:
                print(f"ok       {name}")
        return 1 if bad else 0

    digests: dict[str, str] = {}
    for name in FILES:
        path = fetch(name, force=args.force)
        digest = sha256(path)
        digests[name] = digest
        expected = known.get(name)
        state = "fetched"
        if expected and expected != digest:
            state = "CHANGED upstream"
        elif expected:
            state = "unchanged"
        print(f"{state:<16} {name:<14} {path.stat().st_size:>8} bytes")

    write_checksums(digests)
    print(f"checksums written to {CHECKSUM_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
