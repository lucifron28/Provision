from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.ai_recipes import get_provider
from app.core.database import get_db
from app.core.config import settings
from app.models.recipe_source import RecipeSource
from app.models.user import User
from app.schemas.ingredients import StrictSchema
from app.schemas.recipe_source import SourceRead, SourceReferenceInput, SourceReferenceRead
from app.schemas.themealdb import MealDBAdaptationRead, MealDBDiscoveryRead
from app.services.recipe_sources import discovery_plan, read_reference, remove_reference, source_read, write_reference
from app.services.deepseek_discovery import _discovery_provider_error, discover_recipes
from app.services.deepseek_provider import DeepSeekProvider, DeepSeekProviderError
from app.services.pinned_page_transport import PinnedTLSTransport
from app.services.themealdb import MealDBClient
from app.services.themealdb_ai import adapt_reviewed_meal
from app.services.themealdb_budget import PostgresMealDBBudget
from app.services.themealdb_reviewed import discover_filipino_meals

router = APIRouter()


class DiscoveryPlanInput(StrictSchema):
    query: str = Field(min_length=1, max_length=80)
    allow_broader_web: bool = False
    include_reviewed_general: bool = False


class DiscoveryInput(StrictSchema):
    query: str = Field(min_length=1, max_length=80)
    allow_broader_web: StrictBool = False
    max_results: int = Field(default=10, strict=True, ge=1, le=20)


class MealDBAdaptInput(StrictSchema):
    allow_broader_web: StrictBool = False


class MealDBDiscoveryInput(StrictSchema):
    query: str = Field(min_length=1, max_length=80)
    max_results: int = Field(default=10, strict=True, ge=1, le=20)


def get_mealdb_client():
    if not settings.MEALDB_ENABLED:
        raise HTTPException(503, "MEALDB_DISABLED")
    client = MealDBClient(PinnedTLSTransport(
        user_agent="ProvisionBot/1.0 (https://github.com/lucifron28/Provision)"
    ))
    try:
        yield client
    finally:
        client.close()


def get_mealdb_budget():
    return PostgresMealDBBudget(settings)


@router.get("/", response_model=list[SourceRead])
def sources(response: Response, household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return [source_read(source) for source in db.scalars(select(RecipeSource).order_by(RecipeSource.id)).all()]


@router.post("/discovery-plan")
def plan(request: DiscoveryPlanInput, response: Response, household_id: int = Depends(get_current_household_id),
         db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return discovery_plan(db, request.query, request.allow_broader_web, request.include_reviewed_general)


@router.post("/discover")
def discover(request: DiscoveryInput, response: Response,
             household_id: int = Depends(get_current_household_id),
             user: User = Depends(get_current_user), db: Session = Depends(get_db),
             provider: DeepSeekProvider = Depends(get_provider)):
    response.headers["Cache-Control"] = "no-store"
    return discover_recipes(db, household_id, user.id, request.query,
                            allow_broader_web=request.allow_broader_web,
                            max_results=request.max_results, provider=provider)


@router.post("/mealdb/discover", response_model=MealDBDiscoveryRead)
def discover_meals(request: MealDBDiscoveryInput, response: Response,
                   household_id: int = Depends(get_current_household_id),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db),
                   client: MealDBClient = Depends(get_mealdb_client),
                   budget: PostgresMealDBBudget = Depends(get_mealdb_budget)):
    response.headers["Cache-Control"] = "no-store"
    try:
        return discover_filipino_meals(db, household_id, user.id, request.query,
                                       request.max_results, client=client, budget=budget)
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "budget_unavailable"}) from None


@router.post("/mealdb/{meal_id}/adapt", response_model=MealDBAdaptationRead)
def adapt_meal(meal_id: str, request: MealDBAdaptInput, response: Response,
               household_id: int = Depends(get_current_household_id),
               user: User = Depends(get_current_user), db: Session = Depends(get_db),
               client: MealDBClient = Depends(get_mealdb_client),
               budget: PostgresMealDBBudget = Depends(get_mealdb_budget),
               provider: DeepSeekProvider = Depends(get_provider)):
    response.headers["Cache-Control"] = "no-store"
    if not settings.DEEPSEEK_ENABLED:
        raise HTTPException(503, detail={"code": "disabled"})
    try:
        return adapt_reviewed_meal(db, household_id, user.id, meal_id, client=client,
                                   budget=budget, provider=provider,
                                   allow_broader_web=request.allow_broader_web)
    except DeepSeekProviderError as exc:
        raise _discovery_provider_error(exc) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "budget_unavailable"}) from None


@router.get("/recipes/{recipe_id}/reference", response_model=SourceReferenceRead)
def get_reference(recipe_id: int, response: Response, household_id: int = Depends(get_current_household_id),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_reference(db, household_id, recipe_id)


@router.put("/recipes/{recipe_id}/reference", response_model=SourceReferenceRead)
def put_reference(recipe_id: int, request: SourceReferenceInput, response: Response,
                  household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return write_reference(db, household_id, user.id, recipe_id, request)


@router.delete("/recipes/{recipe_id}/reference", status_code=204)
def delete_reference(recipe_id: int, expected_revision: int = Query(ge=1),
                     household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    remove_reference(db, household_id, user.id, recipe_id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
