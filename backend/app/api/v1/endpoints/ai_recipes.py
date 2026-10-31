"""Explicitly requested AI-original recipe proposals."""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai_recipe import AIRecipeRead, AIRecipeRequest
from app.services.ai_recipes import generate_recipe
from app.services.deepseek_provider import DeepSeekProvider, DeepSeekProviderError
from app.services.deepseek_budget import PostgresDeepSeekBudget

router = APIRouter()


@lru_cache(maxsize=1)
def get_provider():
    return DeepSeekProvider(settings, budget=PostgresDeepSeekBudget(settings))


@router.post("/generate", response_model=AIRecipeRead)
def generate(request: AIRecipeRequest, response: Response,
             household_id: int = Depends(get_current_household_id),
             user: User = Depends(get_current_user), db: Session = Depends(get_db),
             provider: DeepSeekProvider = Depends(get_provider)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return generate_recipe(db, household_id, user.id, request, provider)
    except DeepSeekProviderError as exc:
        if exc.code in {"disabled", "configuration", "budget_unavailable"}:
            status = 503
        elif exc.code in {"rate_limited", "request_budget_exhausted"}:
            status = 429
        elif exc.code == "timeout":
            status = 504
        else:
            status = 502
        raise HTTPException(status_code=status, detail={"code": exc.code}) from None
