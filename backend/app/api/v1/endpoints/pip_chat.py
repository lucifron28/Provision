"""Consent-gated Pip Chat endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.pip_chat import PipChatRead, PipChatRequest
from app.services.deepseek_budget import PostgresDeepSeekBudget
from app.services.deepseek_provider import DeepSeekProvider, DeepSeekProviderError
from app.services.pip_chat import generate_pip_chat

router = APIRouter()


def get_pip_chat_provider(household_id: int = Depends(get_current_household_id)):
    budget = PostgresDeepSeekBudget(settings, household_id=household_id)
    if settings.DEEPSEEK_ENABLED:
        try:
            budget.prepare_household()
        except SQLAlchemyError:
            raise HTTPException(503, detail={"code": "budget_unavailable"}) from None
    with DeepSeekProvider(settings, budget=budget) as provider:
        yield provider


@router.post("/chat", response_model=PipChatRead)
def chat(
    request: PipChatRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: DeepSeekProvider = Depends(get_pip_chat_provider),
) -> PipChatRead:
    response.headers["Cache-Control"] = "no-store"
    try:
        return generate_pip_chat(db, household_id, user.id, request, provider)
    except DeepSeekProviderError as exc:
        if exc.code in {"disabled", "configuration", "budget_unavailable"}:
            status_code = 503
        elif exc.code in {"rate_limited", "request_budget_exhausted"}:
            status_code = 429
        elif exc.code == "timeout":
            status_code = 504
        else:
            status_code = 502
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code},
            headers={"Cache-Control": "no-store"},
        ) from None
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail={"code": "chat_context_unavailable"},
            headers={"Cache-Control": "no-store"},
        ) from None
