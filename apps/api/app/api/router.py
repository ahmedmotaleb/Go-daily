"""Versioned API router."""

from fastapi import APIRouter

from app.api.routes import (
    assignments,
    audit,
    auth,
    dashboard,
    drivers,
    operations,
    shifts,
    users,
    vehicles,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(vehicles.router)
api_router.include_router(drivers.router)
api_router.include_router(assignments.router)
api_router.include_router(operations.router)
api_router.include_router(shifts.router)
api_router.include_router(dashboard.router)
