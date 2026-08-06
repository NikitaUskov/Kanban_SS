"""Public registration/reset and protected invitation administration routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.invitations.schemas import (
    InvitationAccept,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationList,
    InvitationPreview,
    InvitationResponse,
    ManualResetLink,
    PasswordResetConfirm,
    PasswordResetRequest,
)
from app.invitations.service import (
    accept_invitation,
    confirm_password_reset,
    create_invitation,
    create_manual_reset_link,
    list_invitations,
    preview_invitation,
    request_password_reset,
    resend_invitation,
    revoke_invitation,
)
from app.schemas import MessageResponse
from app.users.schemas import UserPublic

router = APIRouter(tags=["Регистрация и приглашения"])
DbSession = Annotated[Session, Depends(get_db)]


def _response(item, url: str | None = None) -> InvitationResponse:
    data = InvitationResponse.model_validate(item).model_dump()
    data["invite_url"] = url
    return InvitationResponse(**data)


@router.get("/auth/invitations/{token}", response_model=InvitationPreview)
def preview_route(token: str, db: DbSession) -> InvitationPreview:
    item = preview_invitation(db, token)
    return InvitationPreview(
        email=item.email,
        display_name=item.display_name,
        expires_at=item.expires_at,
        system_role=item.system_role,
    )


@router.post("/auth/invitations/accept", response_model=InvitationAcceptResponse)
def accept_route(payload: InvitationAccept, db: DbSession) -> InvitationAcceptResponse:
    user = accept_invitation(db, payload)
    return InvitationAcceptResponse(
        user=UserPublic.model_validate(user),
        message="Аккаунт создан. Теперь можно войти",
    )


@router.post("/auth/password-reset/request", response_model=MessageResponse)
def request_reset_route(payload: PasswordResetRequest, db: DbSession) -> MessageResponse:
    request_password_reset(db, payload.email)
    return MessageResponse(message="Если аккаунт с таким email существует, инструкция отправлена")


@router.post("/auth/password-reset/confirm", response_model=MessageResponse)
def confirm_reset_route(payload: PasswordResetConfirm, db: DbSession) -> MessageResponse:
    confirm_password_reset(db, payload.token, payload.new_password)
    return MessageResponse(message="Пароль изменён. Войдите с новым паролем")


@router.get("/admin/invitations", response_model=InvitationList)
def list_route(db: DbSession, user: CurrentUser) -> InvitationList:
    return InvitationList(items=[_response(item) for item in list_invitations(db, user)])


@router.post(
    "/admin/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED
)
def create_route(payload: InvitationCreate, db: DbSession, user: CurrentUser) -> InvitationResponse:
    item, url = create_invitation(db, payload, user)
    return _response(item, url)


@router.post("/admin/invitations/{invitation_id}/resend", response_model=InvitationResponse)
def resend_route(invitation_id: UUID, db: DbSession, user: CurrentUser) -> InvitationResponse:
    item, url = resend_invitation(db, str(invitation_id), user)
    return _response(item, url)


@router.delete("/admin/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_route(invitation_id: UUID, db: DbSession, user: CurrentUser) -> Response:
    revoke_invitation(db, str(invitation_id), user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/users/{user_id}/password-reset-link", response_model=ManualResetLink)
def manual_reset_route(user_id: UUID, db: DbSession, user: CurrentUser) -> ManualResetLink:
    url, record = create_manual_reset_link(db, str(user_id), user)
    return ManualResetLink(reset_url=url, expires_at=record.expires_at)
