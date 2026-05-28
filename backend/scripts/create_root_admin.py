from __future__ import annotations

import os
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import find_dotenv, load_dotenv

from repositories.auth_repo import AuthRepository
from services.auth_service import AuthService


def main() -> None:
    load_dotenv(find_dotenv())
    email = os.getenv("ROOT_ADMIN_EMAIL", "admin@example.com").strip().lower()
    password = os.getenv("ROOT_ADMIN_PASSWORD", "Admin@123456")
    full_name = os.getenv("ROOT_ADMIN_NAME", "System Root Admin")

    repo = AuthRepository()
    existing = repo.find_user_by_email(email)
    if existing:
        current_role = existing.get("account_role")
        if current_role != "root_admin":
            repo.set_user_account_role(str(existing["_id"]), "root_admin")
            print(f"Updated existing user to root_admin: {email}")
        else:
            print(f"Root admin already exists: {email}")
        return

    service = AuthService(repo)
    user = service.create_admin_user(
        {
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": "expert",
        },
        account_role="root_admin",
    )
    print(f"Created root admin: {user['email']} ({user['id']})")


if __name__ == "__main__":
    main()
