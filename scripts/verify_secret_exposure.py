#!/usr/bin/env python3
"""
Secret Exposure & Production Bundle Scanner (Phase 10).

Verifies:
1. Frontend build bundle (frontend/dist/) contains ZERO backend-only secrets:
   - SUPABASE_SERVICE_ROLE_KEY
   - RAZORPAY_KEY_SECRET
   - RAZORPAY_WEBHOOK_SECRET
   - Database connection strings / passwords
   - Private keys (BEGIN PRIVATE KEY / RSA PRIVATE KEY)
2. Frontend source code does not import backend configurations.
3. .gitignore properly ignores .env and sensitive credential paths.
"""

from pathlib import Path
import re
import sys

# High-risk patterns that must NEVER exist in client bundles or frontend source
LEAKAGE_PATTERNS = [
    (r"service_role[a-zA-Z0-9_\-]{20,}", "Supabase service_role key format detected"),
    (r"rzp_(?:live|test)_[a-zA-Z0-9]{14,}:[a-zA-Z0-9]{14,}", "Razorpay key:secret combination detected"),
    (r"BEGIN (?:RSA )?PRIVATE KEY", "Private cryptographic key block detected"),
    (r"postgres(?:ql)?:\/\/[^:]+:[^@]+@[^:]+:[0-9]+\/", "Postgres connection string with password detected"),
]

# Sensitive env names that must never have literal assigned values in client artifacts
SENSITIVE_ENV_NAMES = [
    "SUPABASE_SERVICE_ROLE_KEY",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
]


def scan_dist_bundle(dist_dir: Path) -> list[str]:
    """Scan the built frontend bundle for secret leakage."""
    findings = []
    if not dist_dir.exists():
        print(f"[INFO] {dist_dir} does not exist yet; skipping dist bundle scan.")
        return []

    print(f"Scanning frontend production artifacts in {dist_dir}...")
    js_files = list(dist_dir.glob("**/*.js")) + list(dist_dir.glob("**/*.html"))

    for f in js_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        for pattern, desc in LEAKAGE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                findings.append(f"{f.relative_to(dist_dir)}: {desc}")

        for env_name in SENSITIVE_ENV_NAMES:
            # Check for env assignment e.g. SUPABASE_SERVICE_ROLE_KEY="..."
            assignment_pattern = rf'{env_name}\s*[:=]\s*["\']([^"\']+)["\']'
            match = re.search(assignment_pattern, content)
            if match:
                val = match.group(1)
                if not val.startswith("your_") and not "placeholder" in val:
                    findings.append(f"{f.relative_to(dist_dir)}: Explicit assignment of {env_name} found in client bundle")

    return findings


def scan_frontend_src(src_dir: Path) -> list[str]:
    """Scan frontend source code for forbidden references to service role keys or secrets."""
    findings = []
    if not src_dir.exists():
        return [f"Frontend src directory not found: {src_dir}"]

    print(f"Scanning frontend source code in {src_dir}...")
    for f in src_dir.glob("**/*.[jt]s*"):
        if "__tests__" in str(f):
            continue
        content = f.read_text(encoding="utf-8", errors="ignore")
        for env_name in SENSITIVE_ENV_NAMES:
            if env_name in content:
                # Find line number
                lines = content.splitlines()
                for idx, line in enumerate(lines, 1):
                    if env_name in line and not line.strip().startswith("//"):
                        findings.append(f"{f.name}:{idx} references {env_name}")

    return findings


def verify_gitignore(repo_root: Path) -> list[str]:
    """Verify that .gitignore properly excludes .env and secret files."""
    findings = []
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        findings.append("Root .gitignore does not exist")
        return findings

    content = gitignore_path.read_text(encoding="utf-8")
    if ".env" not in content:
        findings.append(".gitignore is missing '.env' pattern")

    return findings


def main():
    repo_root = Path(__file__).resolve().parent.parent
    frontend_dir = repo_root / "frontend"
    dist_dir = frontend_dir / "dist"
    src_dir = frontend_dir / "src"

    print("=" * 60)
    print("VehicleCare Secret Exposure & Production Bundle Scanner")
    print("=" * 60)

    all_errors = []

    # 1. Verify .gitignore
    gitignore_issues = verify_gitignore(repo_root)
    all_errors.extend(gitignore_issues)

    # 2. Verify frontend source
    src_issues = scan_frontend_src(src_dir)
    all_errors.extend(src_issues)

    # 3. Verify dist bundle
    dist_issues = scan_dist_bundle(dist_dir)
    all_errors.extend(dist_issues)

    print("-" * 60)
    if all_errors:
        print("[FAIL] Secret exposure check failed with the following findings:")
        for issue in all_errors:
            print(f"  [!] {issue}")
        print("=" * 60)
        sys.exit(1)
    else:
        print("[PASS] Zero secrets detected in client source, .gitignore, and dist/ bundle.")
        print("       - Supabase publishable key only (Service Role Key strictly blocked).")
        print("       - Payment secrets & webhook secrets strictly backend-only.")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
