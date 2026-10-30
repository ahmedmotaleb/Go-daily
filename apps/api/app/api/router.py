"""Versioned API router."""

from fastapi import APIRouter

from app.api.routes import (
    assignments,
    attachments,
    audit,
    auth,
    dashboard,
    driver_app,
    driver_finance,
    drivers,
    exceptions,
    expenses,
    fuel,
    maintenance,
    notifications,
    operations,
    profitability,
    reports,
    revenue,
    ride_hailing,
    route_events,
    shifts,
    tracking,
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
api_router.include_router(driver_app.router)
api_router.include_router(tracking.router)
api_router.include_router(route_events.router)
api_router.include_router(fuel.router)
api_router.include_router(expenses.router)
api_router.include_router(revenue.router)
api_router.include_router(ride_hailing.router)
api_router.include_router(driver_finance.router)
api_router.include_router(profitability.router)
api_router.include_router(attachments.router)
api_router.include_router(maintenance.router)
api_router.include_router(exceptions.router)
api_router.include_router(notifications.router)
api_router.include_router(reports.router)
