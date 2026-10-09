"""API v1 router aggregating all endpoint subrouters."""

from fastapi import APIRouter

from app.api.v1.endpoints import calculate, health, root

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(root.router, tags=["System"])
api_router.include_router(calculate.router, tags=["Calculation"])
