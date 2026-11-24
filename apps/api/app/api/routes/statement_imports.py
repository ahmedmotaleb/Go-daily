"""Ride-hailing statement CSV import endpoints (U19)."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, require_permissions
from app.api.finance_presenters import load_users
from app.core.permissions import Permission
from app.models.finance import RecordStatus, RideHailingImportBatch
from app.models.user import User
from app.schemas.finance import (
    ImportBatchOut,
    ImportFieldOut,
    ImportPreviewOut,
    ImportRowOut,
    Ref,
    StatementImportIn,
    UserRef,
    VoidAction,
)
from app.services import statement_import as service

router = APIRouter(prefix="/ride-hailing/imports", tags=["ride-hailing"])

Reader = Annotated[User, Depends(require_permissions(Permission.REVENUE_READ))]
Writer = Annotated[User, Depends(require_permissions(Permission.REVENUE_WRITE))]
Approver = Annotated[User, Depends(require_permissions(Permission.REVENUE_APPROVE))]

FIELDS = [
    ImportFieldOut(key=k, label=label, required=req) for k, (label, req) in service.FIELDS.items()
]


def _batch_out(
    db: DbSession, batch: RideHailingImportBatch, *, full: bool = False
) -> ImportBatchOut:
    users = load_users(db, [batch.created_by_id])
    creator = users.get(batch.created_by_id) if batch.created_by_id else None
    out = ImportBatchOut(
        id=batch.id,
        platform=Ref(id=batch.platform.id, name=batch.platform.name),
        file_name=batch.file_name,
        rows_total=batch.rows_total,
        rows_imported=batch.rows_imported,
        skipped=batch.skipped,
        status=batch.status.value,
        created_by=UserRef(id=creator.id, full_name=creator.full_name) if creator else None,
        created_at=batch.created_at,
        voided_at=batch.voided_at,
        void_reason=batch.void_reason,
    )
    if full:
        rows = service.statements(db, batch.id)
        out.statements = [
            Ref(
                id=s.id,
                name=f"صف {s.import_row} — {s.driver.full_name} — {s.period_start}"
                + (" (ملغي)" if s.status is RecordStatus.VOIDED else ""),
            )
            for s in rows
        ]
        out.pending = sum(1 for s in rows if s.status is RecordStatus.SUBMITTED)
    return out


@router.get("", response_model=list[ImportBatchOut])
def list_imports(_: Reader, db: DbSession) -> list[ImportBatchOut]:
    return [_batch_out(db, b) for b in service.list_batches(db)]


@router.post("/preview", response_model=ImportPreviewOut)
def preview_import(body: StatementImportIn, _: Writer, db: DbSession) -> ImportPreviewOut:
    """Check every row without saving anything."""
    result = service.preview(
        db,
        platform_id=body.platform_id,
        file_name=body.file_name,
        content=body.content,
        mapping=body.mapping,
    )
    return ImportPreviewOut(
        platform_id=result.platform_id,
        file_name=result.file_name,
        headers=result.headers,
        mapping=result.mapping,
        fields=FIELDS,
        rows=[
            ImportRowOut.model_validate({k: v for k, v in asdict(r).items() if k != "data"})
            for r in result.rows
        ],
        counts=result.counts,
        already_imported=result.already_imported,
    )


@router.post("", response_model=ImportBatchOut, status_code=status.HTTP_201_CREATED)
def import_statements(body: StatementImportIn, actor: Writer, db: DbSession) -> ImportBatchOut:
    batch = service.commit(
        db,
        actor=actor,
        platform_id=body.platform_id,
        file_name=body.file_name,
        content=body.content,
        mapping=body.mapping,
    )
    return _batch_out(db, batch, full=True)


@router.get("/{batch_id}", response_model=ImportBatchOut)
def get_import(batch_id: uuid.UUID, _: Reader, db: DbSession) -> ImportBatchOut:
    return _batch_out(db, service.get(db, batch_id), full=True)


@router.post("/{batch_id}/void", response_model=ImportBatchOut)
def void_import(
    batch_id: uuid.UUID, body: VoidAction, actor: Approver, db: DbSession
) -> ImportBatchOut:
    """Roll back the file: every statement it created is voided (and its revenue)."""
    return _batch_out(
        db, service.void(db, actor=actor, batch_id=batch_id, reason=body.reason), full=True
    )
