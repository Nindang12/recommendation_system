from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from repositories.auth_repo import AuthRepository


class AdminAuditLogService:
    """Append-only audit log for admin data governance actions."""

    def __init__(self, repo: Optional[AuthRepository] = None) -> None:
        self.repo = repo or AuthRepository()

    def log(
        self,
        *,
        admin_user_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "admin_user_id": admin_user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before": before or {},
            "after": after or {},
            "reason": reason,
            "created_at": datetime.now(timezone.utc),
        }
        return self.repo.insert_admin_audit_log(payload)
