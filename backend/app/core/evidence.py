"""
Evidence Storage Path Validation Utilities.

Validates that evidence media paths conform to strict storage layout rules:
- Format: {booking_id}/{category}/{filename}
- Bucket: service-evidence (private bucket)
- Strictly prevents path traversal (../), absolute filesystem paths, cross-booking leaks, and invalid characters.
"""

import re
import uuid
from fastapi import HTTPException, status


VALID_FILENAME_REGEX = re.compile(r"^[a-zA-Z0-9._-]+$")
ALLOWED_CATEGORIES = {
    "inspections",
    "additional_work",
    "before_service",
    "after_service",
    "completion",
    "disputes",
}


def validate_evidence_path(
    path: str,
    expected_booking_id: uuid.UUID,
    allowed_categories: set[str] | list[str] | None = None,
) -> str:
    """
    Validate and sanitize an evidence storage path.

    Rules:
    - Path must not be empty.
    - No path traversal (e.g. '../', '..').
    - No absolute paths (cannot start with '/' or Windows drive letters).
    - Must follow format: {booking_id}/{category}/{filename}
    - Root folder segment must match expected_booking_id exactly (anti cross-booking).
    - Category must match one of the allowed categories.
    - Filename must match alphanumeric, dot, underscore, hyphen format.

    Returns:
        Cleaned path string.

    Raises:
        HTTPException(400): If any validation constraint is violated.
    """
    if not path or not isinstance(path, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Evidence file path must be a non-empty string.",
        )

    # Normalize backslashes to forward slashes
    clean_path = path.replace("\\", "/").strip()

    # Reject traversal attempts
    if ".." in clean_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal (..) is strictly prohibited in evidence file paths.",
        )

    # Reject absolute root or drive letter paths
    if clean_path.startswith("/") or (len(clean_path) > 1 and clean_path[1] == ":"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Absolute file paths are not permitted for evidence storage.",
        )

    parts = clean_path.split("/")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid evidence path format: '{path}'. "
                "Expected format: '{booking_id}/{category}/{filename}'"
            ),
        )

    folder_booking_str, category, filename = parts

    # Verify booking UUID in path
    try:
        folder_booking_id = uuid.UUID(folder_booking_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid booking UUID segment in evidence path: '{folder_booking_str}'.",
        )

    if folder_booking_id != expected_booking_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cross-booking evidence path violation: Path specifies booking '{folder_booking_id}' "
                f"but target booking is '{expected_booking_id}'."
            ),
        )

    # Verify category
    valid_cats = set(allowed_categories) if allowed_categories else ALLOWED_CATEGORIES
    if category not in valid_cats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid evidence category '{category}'. "
                f"Allowed categories: {sorted(list(valid_cats))}"
            ),
        )

    # Verify filename
    if not filename or not VALID_FILENAME_REGEX.match(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid evidence filename: '{filename}'. Only alphanumeric, '.', '_', and '-' are allowed.",
        )

    return f"{folder_booking_id}/{category}/{filename}"


def validate_evidence_paths(
    paths: list[str] | None,
    expected_booking_id: uuid.UUID,
    allowed_categories: set[str] | list[str] | None = None,
) -> list[str]:
    """Validate a list of evidence file paths."""
    if not paths:
        return []
    return [
        validate_evidence_path(p, expected_booking_id, allowed_categories=allowed_categories)
        for p in paths
    ]
