"""System and board access checks."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import BoardMember, User

SYSTEM_ADMIN_ROLES = {"owner", "admin"}
BOARD_ROLE_RANK = {"viewer": 1, "editor": 2, "admin": 3}


def is_system_admin(user: User) -> bool:
    return user.role in SYSTEM_ADMIN_ROLES


def require_system_admin(user: User) -> None:
    if not is_system_admin(user):
        raise AppError(403, "ADMIN_REQUIRED", "Требуются права администратора")


def require_owner(user: User) -> None:
    if user.role != "owner":
        raise AppError(403, "OWNER_REQUIRED", "Действие доступно только владельцу")


def get_board_role(db: Session, board_id: str, user: User) -> str | None:
    if is_system_admin(user):
        return "admin"
    return db.scalar(
        select(BoardMember.role).where(
            BoardMember.board_id == board_id,
            BoardMember.user_id == user.id,
        )
    )


def require_board_access(db: Session, board_id: str, user: User, minimum: str = "viewer") -> str:
    role = get_board_role(db, board_id, user)
    if role is None:
        raise AppError(403, "BOARD_ACCESS_DENIED", "У вас нет доступа к этой доске")
    if BOARD_ROLE_RANK[role] < BOARD_ROLE_RANK[minimum]:
        raise AppError(
            403,
            "BOARD_ROLE_INSUFFICIENT",
            "Недостаточно прав для выполнения операции",
            {"requiredRole": minimum, "currentRole": role},
        )
    return role
