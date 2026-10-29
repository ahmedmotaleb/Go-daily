"""Operational command-line interface.

    python -m app.cli seed              # idempotent reference data
    python -m app.cli bootstrap-admin   # first SUPER_ADMIN from env vars

Seeding only inserts reference/lookup data (e.g. vehicle types). It never
creates fake operational, GPS or financial records.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.db import SessionLocal

Seeder = Callable[[Session], int]

# Each seeder inserts missing rows and returns how many it created.
SEEDERS: list[tuple[str, Seeder]] = []


def cmd_seed(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        for name, seeder in SEEDERS:
            created = seeder(db)
            print(f"seed {name}: {created} created")
        db.commit()
    if not SEEDERS:
        print("No reference data to seed yet.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="Go Daily operations CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Insert reference data (idempotent)").set_defaults(func=cmd_seed)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
