from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.schemas.attention_rule import (
    AttentionRuleCreate,
    AttentionRuleListResponse,
    AttentionRuleResponse,
    AttentionRuleUpdate,
)
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
