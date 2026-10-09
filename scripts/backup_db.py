#!/usr/bin/env python
r"""SQLite database backup utility.

Usage:
    python scripts/backup_db.py              # Backup to data/backups/
    python scripts/backup_db.py --keep 7     # Keep only last 7 backups

Can be scheduled via cron (Linux) or Task Scheduler (Windows):
    # Linux cron - daily at 2 AM
    0 2 * * * cd /app && python scripts/backup_db.py --keep 30

    # Windows Task Scheduler - daily at 2 AM
    schtasks /create /tn "StockPilot Backup" /tr "python D:\StockPilot\scripts\backup_db.py --keep 30" /sc daily /st 02:00
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import DB_PATH  # noqa: E402

BACKUP_DIR = PROJECT_ROOT / "data" / "backups"


def create_backup() -> Path:
    """Create a timestamped backup of the SQLite database."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"stockpilot_{timestamp}.db"

    if not Path(DB_PATH).exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    # Use SQLite's backup API for a consistent snapshot
    import sqlite3

    source = sqlite3.connect(str(DB_PATH))
    dest = sqlite3.connect(str(backup_path))
    source.backup(dest)
    dest.close()
    source.close()

    size_kb = backup_path.stat().st_size / 1024
    print(f"Backup created: {backup_path.name} ({size_kb:.1f} KB)")
    return backup_path


def cleanup_old_backups(keep: int) -> None:
    """Remove old backups, keeping only the most recent `keep` count."""
    backups = sorted(BACKUP_DIR.glob("stockpilot_*.db"), key=lambda p: p.name, reverse=True)
    if len(backups) <= keep:
        return
    for old in backups[keep:]:
        old.unlink()
        print(f"Removed old backup: {old.name}")


def main():
    parser = argparse.ArgumentParser(description="StockPilot database backup")
    parser.add_argument("--keep", type=int, default=30, help="Number of backups to keep (default: 30)")
    args = parser.parse_args()

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Starting backup...")
    create_backup()
    cleanup_old_backups(args.keep)
    print("Done.")


if __name__ == "__main__":
    main()
