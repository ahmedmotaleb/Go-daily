"""Versioned API router."""

from fastapi import APIRouter

from app.api.routes import assignments, audit, auth, drivers, users, vehicles

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(audit.router)
api_router.include_router(vehicles.router)
api_router.include_router(drivers.router)
api_router.include_router(assignments.router)
