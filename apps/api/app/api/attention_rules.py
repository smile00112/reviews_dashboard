from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.schemas.attention_rule import (
    AttentionEventListResponse,
    AttentionEventResponse,
    AttentionRuleCreate,
    AttentionRuleListResponse,
    AttentionRuleResponse,
    AttentionRuleRestartResponse,
    AttentionRuleUpdate,
)
from app.services.attention_evaluator import AttentionEvaluator
from app.services.attention_rule_service import AttentionRuleService, AttentionRuleValidationError

router = APIRouter(prefix="/api/attention-rules", tags=["attention-rules"])


@router.get("", response_model=AttentionRuleListResponse)
def list_rules(
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> AttentionRuleListResponse:
    items = [AttentionRuleResponse.model_validate(r) for r in AttentionRuleService(db).list_rules()]
    return AttentionRuleListResponse(items=items)


@router.post("", response_model=AttentionRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: AttentionRuleCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> AttentionRuleResponse:
    try:
        return AttentionRuleResponse.model_validate(AttentionRuleService(db).create(payload))
    except AttentionRuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{rule_id}", response_model=AttentionRuleResponse)
def update_rule(
    rule_id: UUID,
    payload: AttentionRuleUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> AttentionRuleResponse:
    try:
        rule = AttentionRuleService(db).update(rule_id, payload)
    except AttentionRuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    return AttentionRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> None:
    if not AttentionRuleService(db).delete(rule_id):
        raise HTTPException(status_code=404, detail="Правило не найдено")


@router.post("/{rule_id}/restart", response_model=AttentionRuleRestartResponse)
def restart_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
) -> AttentionRuleRestartResponse:
    """Сбросить окно правила и переоценить его синхронно (feature 015)."""
    result = AttentionEvaluator(db).restart(rule_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    return AttentionRuleRestartResponse(
        rule=AttentionRuleResponse.model_validate(result.rule),
        events=[AttentionEventResponse.model_validate(e) for e in result.events],
    )


@router.get("/{rule_id}/events", response_model=AttentionEventListResponse)
def list_rule_events(
    rule_id: UUID,
    limit: int = 50,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
) -> AttentionEventListResponse:
    service = AttentionRuleService(db)
    if service.get(rule_id) is None:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    events = service.list_events(rule_id, limit=limit)
    return AttentionEventListResponse(
        items=[AttentionEventResponse.model_validate(e) for e in events]
    )
