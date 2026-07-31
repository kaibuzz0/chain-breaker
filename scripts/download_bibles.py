
#!/usr/bin/env python3
"""Stub downloader for scripture collections.

Users must supply their own legally sourced texts. This script only creates
the expected directory layout.
"""

from pathlib import Path


def main() -> None:
    base = Path("user-scripture-collection")
    base.mkdir(parents=True, exist_ok=True)
    print(f"Place your legally sourced texts in: {base.resolve()}")


if __name__ == "__main__":
    main()
