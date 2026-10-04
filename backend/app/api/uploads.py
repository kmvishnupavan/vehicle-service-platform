"""
Storage & Uploads API.

Mounts under /api/v1/uploads.
Provides guidance and signed path generation for storage buckets.
Enforces the hardened storage policy: {booking_id}/{filename}.
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends
from app.db.dependencies import get_current_user
from app.schemas.user import AuthenticatedUser

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.get("/rules", summary="Get storage path and upload rules")
async def get_storage_rules(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns storage constraints and expected path conventions for private buckets:
    - service-reports: {booking_id}/{filename}
    - service-evidence: {booking_id}/{filename}
    - chat-attachments: {booking_id}/{filename}
    - mechanic-documents: {mechanic_user_id}/{filename}
    - avatars: {user_id}/{filename}
    """
    return {
        "buckets": {
            "service-reports": {
                "public": False,
                "path_pattern": "{booking_id}/{filename}",
                "allowed_roles": ["customer", "mechanic", "admin", "support"],
            },
            "service-evidence": {
                "public": False,
                "path_pattern": "{booking_id}/{filename}",
                "allowed_roles": ["customer", "mechanic", "admin", "support"],
            },
            "chat-attachments": {
                "public": False,
                "path_pattern": "{booking_id}/{filename}",
                "allowed_roles": ["customer", "mechanic", "admin", "support"],
            },
            "mechanic-documents": {
                "public": False,
                "path_pattern": "{mechanic_user_id}/{filename}",
                "allowed_roles": ["mechanic", "admin"],
            },
            "avatars": {
                "public": True,
                "path_pattern": "{user_id}/{filename}",
                "allowed_roles": ["customer", "mechanic", "admin", "support"],
            },
        },
        "max_file_size_mb": 10,
        "direct_upload_url": "Upload directly to Supabase Storage using client JWT.",
    }
