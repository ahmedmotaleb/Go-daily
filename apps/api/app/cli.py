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

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.services.exceptions import redact_old_evidence, run_detection
from app.services.idempotency import prune
from app.services.notifications import generate as generate_notifications
from app.services.tracking import prune_old_points
from app.services.users import bootstrap_super_admin

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


def cmd_bootstrap_admin(_: argparse.Namespace) -> int:
    """Create the first SUPER_ADMIN from BOOTSTRAP_ADMIN_* environment variables."""
    settings = get_settings()
    password = (
        settings.bootstrap_admin_password.get_secret_value()
        if settings.bootstrap_admin_password
        else ""
    )
    if not settings.bootstrap_admin_phone or not password:
        print(
            "Set BOOTSTRAP_ADMIN_PHONE and BOOTSTRAP_ADMIN_PASSWORD (and optionally "
            "BOOTSTRAP_ADMIN_NAME) in the environment.",
            file=sys.stderr,
        )
        return 2
    with SessionLocal() as db:
        try:
            user = bootstrap_super_admin(
                db,
                full_name=settings.bootstrap_admin_name,
                phone=settings.bootstrap_admin_phone,
                password=password,
            )
        except (DomainError, ValueError) as exc:
            print(f"bootstrap-admin failed: {exc}", file=sys.stderr)
            return 1
    print(
        f"Created SUPER_ADMIN {user.phone} ({user.id}). Remove the password from the environment."
    )
    return 0


def cmd_prune_gps(args: argparse.Namespace) -> int:
    """Delete raw GPS points of finished shifts older than the retention period."""
    days = args.older_than_days or get_settings().gps_retention_days
    with SessionLocal() as db:
        deleted = prune_old_points(db, older_than_days=days)
        redacted = redact_old_evidence(db, older_than_days=days)
    print(f"Deleted {deleted} GPS points older than {days} days.")
    print(f"Removed coordinates from {redacted} closed review cases older than {days} days.")
    return 0


def cmd_prune_idempotency(_: argparse.Namespace) -> int:
    with SessionLocal() as db:
        print(f"Deleted {prune(db)} expired idempotency records.")
    return 0


def cmd_detect_exceptions(args: argparse.Namespace) -> int:
    """Run the exception rules over the last N days (safe to repeat; schedule it hourly)."""
    with SessionLocal() as db:
        try:
            run = run_detection(db, actor=None, trigger="cli", days=args.days)
        except DomainError as exc:
            print(f"detect-exceptions: {exc}", file=sys.stderr)
            return 1
    found = sum(r.get("found", 0) for r in run.results.values())
    new = sum(r.get("new", 0) for r in run.results.values())
    print(f"Exception rules found {found} cases ({new} new).")
    for rule, error in run.errors.items():
        print(f"  rule {rule} failed: {error}", file=sys.stderr)
    return 1 if run.errors else 0


def cmd_generate_notifications(_: argparse.Namespace) -> int:
    """Create in-app notifications from the current state (safe to repeat; run hourly)."""
    with SessionLocal() as db:
        outcome = generate_notifications(db)
    new = sum(r.get("new", 0) for r in outcome["results"].values())
    cleared = sum(r.get("cleared", 0) for r in outcome["results"].values())
    print(f"Notifications: {new} new, {cleared} cleared.")
    for kind, error in outcome["errors"].items():
        print(f"  generator {kind} failed: {error}", file=sys.stderr)
    return 1 if outcome["errors"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="Go Daily operations CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Insert reference data (idempotent)").set_defaults(func=cmd_seed)
    sub.add_parser(
        "bootstrap-admin", help="Create the first SUPER_ADMIN from BOOTSTRAP_ADMIN_* env vars"
    ).set_defaults(func=cmd_bootstrap_admin)
    prune = sub.add_parser("prune-gps", help="Delete raw GPS points past the retention period")
    prune.add_argument("--older-than-days", type=int, default=None)
    prune.set_defaults(func=cmd_prune_gps)
    sub.add_parser("prune-idempotency", help="Delete expired idempotency records").set_defaults(
        func=cmd_prune_idempotency
    )
    detect = sub.add_parser("detect-exceptions", help="Run the operational exception rules")
    detect.add_argument("--days", type=int, default=None, help="Look-back window (default 3)")
    detect.set_defaults(func=cmd_detect_exceptions)
    sub.add_parser(
        "generate-notifications", help="Create in-app notifications from the current state"
    ).set_defaults(func=cmd_generate_notifications)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
