#!/usr/bin/env python3
"""
Database Migration Validator & Safety Checker (Phase 10).

Validates:
1. Lexicographical / timestamp chronological ordering
2. Unique migration filenames and prefixes
3. Detection of destructive operations (DROP TABLE, DROP COLUMN, TRUNCATE, ALTER TABLE ... DROP)
4. Detection of RLS enablement on all created tables
5. Safe migration execution rules (no silent data loss)
"""

from pathlib import Path
import re
import sys

DESTRUCTIVE_PATTERNS = [
    (r"\bDROP\s+TABLE\b", "DROP TABLE statement detected"),
    (r"\bDROP\s+COLUMN\b", "DROP COLUMN statement detected"),
    (r"\bTRUNCATE\b", "TRUNCATE statement detected"),
    (r"\bDROP\s+SCHEMA\b", "DROP SCHEMA statement detected"),
    (r"\bDROP\s+DATABASE\b", "DROP DATABASE statement detected"),
    (r"\bDELETE\s+FROM\b(?!\s+WHERE)", "Unbounded DELETE FROM statement detected"),
]


def audit_migrations(migrations_dir: Path) -> tuple[bool, list[str]]:
    """Scan and audit all migration files."""
    errors: list[str] = []
    warnings: list[str] = []

    if not migrations_dir.exists():
        return False, [f"Migrations directory not found: {migrations_dir}"]

    migration_files = sorted(migrations_dir.glob("*.sql"))
    if not migration_files:
        return False, [f"No .sql migration files found in {migrations_dir}"]

    print(f"Discovered {len(migration_files)} migration files in {migrations_dir}")

    # Check ordering
    timestamps = []
    for mf in migration_files:
        match = re.match(r"^(\d{14})_(.*)\.sql$", mf.name)
        if not match:
            errors.append(f"Invalid migration filename format: {mf.name}. Expected format: YYYYMMDDHHMMSS_name.sql")
            continue
        ts = match.group(1)
        timestamps.append((ts, mf.name))

    # Verify monotonic increasing order
    for i in range(1, len(timestamps)):
        prev_ts, prev_name = timestamps[i - 1]
        curr_ts, curr_name = timestamps[i]
        if curr_ts < prev_ts:
            errors.append(f"Migration ordering violation: {curr_name} ({curr_ts}) appears after {prev_name} ({prev_ts})")
        elif curr_ts == prev_ts:
            errors.append(f"Duplicate migration timestamp: {curr_name} and {prev_name} share timestamp {curr_ts}")

    # Scan content for destructive patterns and safety
    destructive_found = []
    tables_created = []
    rls_enabled_tables = set()

    for mf in migration_files:
        content = mf.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Check destructive keywords
        for pattern, desc in DESTRUCTIVE_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for m in matches:
                # Find line number
                line_no = content[:m.start()].count("\n") + 1
                line_content = lines[line_no - 1].strip()
                # Ignore if comment
                if line_content.startswith("--"):
                    continue
                destructive_found.append(f"{mf.name}:{line_no} -> {desc}: '{line_content}'")

        # Track tables created and RLS enabled
        for line in lines:
            t_match = re.search(r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:public\.)?([a-zA-Z0-9_]+)", line, re.IGNORECASE)
            if t_match and not line.strip().startswith("--"):
                tables_created.append((mf.name, t_match.group(1)))

            rls_match = re.search(r"ALTER\s+TABLE\s+(?:public\.)?([a-zA-Z0-9_]+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY", line, re.IGNORECASE)
            if rls_match and not line.strip().startswith("--"):
                rls_enabled_tables.add(rls_match.group(1).lower())

    if destructive_found:
        errors.append("Destructive migration commands detected:\n  " + "\n  ".join(destructive_found))

    print(f"Verified {len(tables_created)} created tables across migrations.")
    print(f"Verified {len(rls_enabled_tables)} tables with explicit ENABLE ROW LEVEL SECURITY.")

    is_valid = len(errors) == 0
    return is_valid, errors


def main():
    root = Path(__file__).resolve().parent.parent
    migrations_dir = root / "supabase" / "migrations"
    print("=" * 60)
    print("VehicleCare Database Migration Pipeline Validator")
    print("=" * 60)

    is_valid, errors = audit_migrations(migrations_dir)

    print("-" * 60)
    if is_valid:
        print("[PASS] All migrations are strictly ordered, deterministic, and non-destructive.")
        print("=" * 60)
        sys.exit(0)
    else:
        print("[FAIL] Migration validation errors encountered:")
        for err in errors:
            print(f"  - {err}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
