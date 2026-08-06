"""Invitation registration and password-reset business logic."""

import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.access import require_board_access, require_system_admin
from app.activity.service import add_activity
from app.auth.security import hash_password, hash_token
from app.config import get_settings
from app.emailer import EmailDeliveryError, send_email
from app.errors import AppError
from app.models import Board, BoardMember, PasswordResetToken, RefreshToken, User, UserInvitation
from app.notifications.service import add_notification
from app.timeutils import as_utc, utcnow
from app.users.schemas import clean_email
from app.users.service import normalize_display_name, normalize_username


def _front_url(param: str, token: str) -> str:
    return f"{get_settings().frontend_url}?{param}={token}"


def _invitation_status(invitation: UserInvitation) -> str:
    if invitation.revoked_at:
        return "revoked"
    if invitation.accepted_at:
        return "accepted"
    if as_utc(invitation.expires_at) <= utcnow():
        return "expired"
    return "pending"


def _validate_board_access(db: Session, actor: User, access: list[dict[str, str]]) -> None:
    seen: set[str] = set()
    for item in access:
        board_id = item["board_id"]
        if board_id in seen:
            raise AppError(400, "BOARD_ACCESS_DUPLICATE", "Доска повторяется в приглашении")
        seen.add(board_id)
        board = db.scalar(select(Board).where(Board.id == board_id, Board.archived_at.is_(None)))
        if board is None:
            raise AppError(404, "BOARD_NOT_FOUND", "Доска из приглашения не найдена")
        require_board_access(db, board_id, actor, "admin")


def create_invitation(db: Session, payload, actor: User) -> tuple[UserInvitation, str]:
    require_system_admin(actor)
    if payload.system_role == "admin" and actor.role != "owner":
        raise AppError(403, "OWNER_REQUIRED", "Только владелец может приглашать администратора")
    email = clean_email(payload.email)
    if email is None:
        raise AppError(400, "EMAIL_INVALID", "Некорректный email")
    if db.scalar(select(User.id).where(User.email_normalized == email)) is not None:
        raise AppError(409, "EMAIL_EXISTS", "Пользователь с таким email уже существует")
    active_invitation = db.scalar(
        select(UserInvitation).where(
            UserInvitation.email_normalized == email,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.revoked_at.is_(None),
            UserInvitation.expires_at > utcnow(),
        )
    )
    if active_invitation is not None:
        raise AppError(409, "INVITATION_EXISTS", "Для этого email уже есть активное приглашение")
    access = [{"board_id": str(item.board_id), "role": item.role} for item in payload.board_access]
    _validate_board_access(db, actor, access)
    raw_token = secrets.token_urlsafe(32)
    invitation = UserInvitation(
        email=email,
        email_normalized=email,
        display_name=normalize_display_name(payload.display_name),
        system_role=payload.system_role,
        board_access_json=access,
        token_hash=hash_token(raw_token),
        created_by_user_id=actor.id,
        expires_at=utcnow() + timedelta(hours=get_settings().invitation_expire_hours),
    )
    db.add(invitation)
    db.flush()
    invite_url = _front_url("invite", raw_token)
    if payload.send_email:
        try:
            sent = send_email(
                email,
                "Приглашение в Kanban Board",
                (
                    f"Здравствуйте, {invitation.display_name}!\n\n"
                    "Вас пригласили в Kanban Board. Откройте ссылку и задайте пароль:\n"
                    f"{invite_url}\n\n"
                    f"Ссылка действует до {invitation.expires_at.isoformat()}."
                ),
            )
            invitation.email_status = "sent" if sent else "disabled"
            invitation.email_sent_at = utcnow() if sent else None
        except EmailDeliveryError as exc:
            invitation.email_status = "failed"
            invitation.email_error = str(exc)[:2000]
    else:
        invitation.email_status = "created"
    add_activity(
        db,
        board_id=None,
        actor_user_id=actor.id,
        action="invitation.created",
        entity_type="invitation",
        entity_id=invitation.id,
        summary=f"Создано приглашение для {email}",
        details={"systemRole": invitation.system_role, "boardAccess": access},
    )
    db.commit()
    db.refresh(invitation)
    return invitation, invite_url


def list_invitations(db: Session, actor: User) -> list[UserInvitation]:
    require_system_admin(actor)
    return list(db.scalars(select(UserInvitation).order_by(UserInvitation.created_at.desc())).all())


def revoke_invitation(db: Session, invitation_id: str, actor: User) -> UserInvitation:
    require_system_admin(actor)
    invitation = db.scalar(select(UserInvitation).where(UserInvitation.id == invitation_id))
    if invitation is None:
        raise AppError(404, "INVITATION_NOT_FOUND", "Приглашение не найдено")
    if invitation.accepted_at:
        raise AppError(409, "INVITATION_ACCEPTED", "Принятое приглашение нельзя отозвать")
    if invitation.revoked_at is None:
        invitation.revoked_at = utcnow()
        add_activity(
            db,
            board_id=None,
            actor_user_id=actor.id,
            action="invitation.revoked",
            entity_type="invitation",
            entity_id=invitation.id,
            summary=f"Приглашение для {invitation.email} отозвано",
        )
        db.commit()
        db.refresh(invitation)
    return invitation


def resend_invitation(db: Session, invitation_id: str, actor: User) -> tuple[UserInvitation, str]:
    require_system_admin(actor)
    invitation = db.scalar(select(UserInvitation).where(UserInvitation.id == invitation_id))
    if invitation is None:
        raise AppError(404, "INVITATION_NOT_FOUND", "Приглашение не найдено")
    if _invitation_status(invitation) in {"accepted", "revoked"}:
        raise AppError(409, "INVITATION_UNAVAILABLE", "Приглашение уже недоступно")
    raw_token = secrets.token_urlsafe(32)
    invitation.token_hash = hash_token(raw_token)
    invitation.expires_at = utcnow() + timedelta(hours=get_settings().invitation_expire_hours)
    invitation.email_error = None
    invite_url = _front_url("invite", raw_token)
    try:
        sent = send_email(
            invitation.email,
            "Повторное приглашение в Kanban Board",
            f"Откройте ссылку для регистрации:\n{invite_url}",
        )
        invitation.email_status = "sent" if sent else "disabled"
        invitation.email_sent_at = utcnow() if sent else None
    except EmailDeliveryError as exc:
        invitation.email_status = "failed"
        invitation.email_error = str(exc)[:2000]
    invitation.updated_at = utcnow()
    db.commit()
    db.refresh(invitation)
    return invitation, invite_url


def preview_invitation(db: Session, token: str) -> UserInvitation:
    invitation = db.scalar(
        select(UserInvitation).where(UserInvitation.token_hash == hash_token(token))
    )
    if invitation is None:
        raise AppError(404, "INVITATION_NOT_FOUND", "Приглашение не найдено")
    status = _invitation_status(invitation)
    if status != "pending":
        messages = {
            "accepted": "Приглашение уже использовано",
            "revoked": "Приглашение отозвано",
            "expired": "Срок действия приглашения истёк",
        }
        raise AppError(410, f"INVITATION_{status.upper()}", messages[status])
    return invitation


def accept_invitation(db: Session, payload) -> User:
    invitation = preview_invitation(db, payload.token)
    username = normalize_username(payload.username)
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise AppError(409, "USERNAME_EXISTS", "Такой логин уже используется")
    if (
        db.scalar(select(User.id).where(User.email_normalized == invitation.email_normalized))
        is not None
    ):
        raise AppError(409, "EMAIL_EXISTS", "Аккаунт с таким email уже существует")
    user = User(
        username=username,
        display_name=normalize_display_name(payload.display_name or invitation.display_name),
        email=invitation.email,
        email_normalized=invitation.email_normalized,
        email_verified_at=utcnow(),
        role=invitation.system_role,
        password_hash=hash_password(payload.password),
        is_active=True,
        notification_settings={},
    )
    db.add(user)
    db.flush()
    for item in invitation.board_access_json:
        board = db.scalar(select(Board).where(Board.id == item.get("board_id")))
        if board is None:
            continue
        db.add(
            BoardMember(
                board_id=board.id,
                user_id=user.id,
                role=item.get("role", "editor"),
                created_by_user_id=invitation.created_by_user_id,
            )
        )
        add_notification(
            db,
            user_id=user.id,
            type="board_added",
            title="Добавлена доска",
            message=f"Вам предоставлен доступ к доске «{board.title}»",
            actor_user_id=invitation.created_by_user_id,
            board_id=board.id,
        )
    invitation.accepted_at = utcnow()
    invitation.updated_at = utcnow()
    add_activity(
        db,
        board_id=None,
        actor_user_id=invitation.created_by_user_id,
        action="invitation.accepted",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.display_name} принял приглашение",
    )
    db.commit()
    db.refresh(user)
    return user


def _new_reset_token(db: Session, user: User) -> tuple[PasswordResetToken, str]:
    raw = secrets.token_urlsafe(32)
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utcnow())
    )
    record = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=utcnow() + timedelta(minutes=get_settings().password_reset_expire_minutes),
    )
    db.add(record)
    db.flush()
    return record, raw


def request_password_reset(db: Session, email: str) -> None:
    normalized = clean_email(email)
    if not normalized or not get_settings().email_enabled:
        return
    user = db.scalar(
        select(User).where(User.email_normalized == normalized, User.is_active.is_(True))
    )
    if user is None:
        return
    record, raw = _new_reset_token(db, user)
    reset_url = _front_url("reset-password", raw)
    try:
        send_email(
            user.email or normalized,
            "Восстановление пароля Kanban Board",
            f"Откройте ссылку для смены пароля:\n{reset_url}\n\nСсылка действует до {record.expires_at.isoformat()}.",
        )
    except EmailDeliveryError:
        db.rollback()
        return
    db.commit()


def create_manual_reset_link(
    db: Session, user_id: str, actor: User
) -> tuple[str, PasswordResetToken]:
    require_system_admin(actor)
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "Пользователь не найден")
    record, raw = _new_reset_token(db, user)
    db.commit()
    db.refresh(record)
    return _front_url("reset-password", raw), record


def confirm_password_reset(db: Session, token: str, new_password: str) -> User:
    record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    if record is None or record.used_at is not None:
        raise AppError(400, "RESET_TOKEN_INVALID", "Ссылка восстановления недействительна")
    if as_utc(record.expires_at) <= utcnow():
        raise AppError(410, "RESET_TOKEN_EXPIRED", "Срок действия ссылки истёк")
    user = db.scalar(select(User).where(User.id == record.user_id))
    if user is None or not user.is_active:
        raise AppError(400, "RESET_USER_UNAVAILABLE", "Учётная запись недоступна")
    user.password_hash = hash_password(new_password)
    user.updated_at = utcnow()
    record.used_at = utcnow()
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()
    db.refresh(user)
    return user
