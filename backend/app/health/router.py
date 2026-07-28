"""Unauthenticated liveness and readiness routes."""

from fastapi import APIRouter

from app.health.schemas import HealthResponse, ReadyResponse
from app.health.service import health, ready

router = APIRouter(tags=["Состояние"])


@router.get("/health", response_model=HealthResponse)
def health_route() -> HealthResponse:
    return health()


@router.get("/ready", response_model=ReadyResponse)
def ready_route() -> ReadyResponse:
    return ready()
