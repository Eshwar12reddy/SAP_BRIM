import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.schemas.memory import (
    MemoryResponse,
    MemoryUpdate,
    MemoryListResponse,
    ScenarioMemoryResponse,
    ScenarioUpdate,
    MemorySettingsResponse,
    MemorySettingsUpdate,
)
from backend.app.security.auth import get_current_user
from backend.app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["Memory Management"])


@router.get("/settings", response_model=MemorySettingsResponse)
def get_memory_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the memory enabled setting for the authenticated user."""
    enabled = memory_service.get_user_memory_enabled(db, current_user.id)
    return MemorySettingsResponse(memory_enabled=enabled)


@router.patch("/settings", response_model=MemorySettingsResponse)
def update_memory_settings(
    settings_in: MemorySettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable or disable persistent memory for the authenticated user."""
    enabled = memory_service.set_user_memory_enabled(db, current_user.id, settings_in.memory_enabled)
    return MemorySettingsResponse(memory_enabled=enabled)


@router.get("", response_model=MemoryListResponse)
def list_memories(
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (active, superseded, etc.)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List persistent memories for the authenticated user (paginated)."""
    items, total = memory_service.list_memories(
        db,
        user_id=current_user.id,
        memory_type=memory_type,
        status=status_filter,
        limit=limit,
        offset=offset
    )
    return MemoryListResponse(
        items=[MemoryResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{memory_id}", response_model=MemoryResponse)
def get_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve a single memory record belonging to the authenticated user."""
    mem = memory_service.get_memory(db, current_user.id, memory_id)
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory record not found"
        )
    return MemoryResponse.model_validate(mem)


@router.patch("/{memory_id}", response_model=MemoryResponse)
def correct_memory(
    memory_id: str,
    update_in: MemoryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update or correct a memory record. Fails with 404 if not found or unauthorized."""
    mem = memory_service.update_memory(
        db,
        user_id=current_user.id,
        memory_id=memory_id,
        summary=update_in.summary,
        memory_type=update_in.memory_type,
        status=update_in.status,
        entities=update_in.entities
    )
    if not mem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory record not found"
        )
    return MemoryResponse.model_validate(mem)


@router.delete("/{memory_id}", status_code=status.HTTP_200_OK)
def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a single memory record belonging to the authenticated user."""
    deleted = memory_service.delete_memory(db, current_user.id, memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory record not found"
        )
    return {"status": "deleted", "id": memory_id}


@router.delete("", status_code=status.HTTP_200_OK)
def delete_all_memories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Purge all persistent cross-chat memory records for the authenticated user."""
    count = memory_service.delete_all_user_memories(db, current_user.id)
    return {"status": "deleted", "count": count, "message": "All user memories cleared successfully"}


@router.get("/scenarios/all", response_model=List[ScenarioMemoryResponse])
def list_scenarios(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List structured SAP BRIM incident/scenario memories for the authenticated user."""
    items, _ = memory_service.list_scenarios(
        db,
        user_id=current_user.id,
        status=status_filter,
        limit=limit,
        offset=offset
    )
    return [ScenarioMemoryResponse.model_validate(item) for item in items]


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioMemoryResponse)
def update_scenario(
    scenario_id: str,
    update_in: ScenarioUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update or resolve an SAP scenario memory."""
    scen = memory_service.update_scenario(
        db,
        user_id=current_user.id,
        scenario_id=scenario_id,
        updates=update_in.model_dump(exclude_unset=True)
    )
    if not scen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario record not found"
        )
    return ScenarioMemoryResponse.model_validate(scen)


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_200_OK)
def delete_scenario(
    scenario_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an SAP scenario memory."""
    deleted = memory_service.delete_scenario(db, current_user.id, scenario_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario record not found"
        )
    return {"status": "deleted", "id": scenario_id}
