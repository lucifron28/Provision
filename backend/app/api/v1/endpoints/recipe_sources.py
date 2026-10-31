from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.ai_recipes import get_provider
from app.core.database import get_db
from app.models.recipe_source import RecipeSource
from app.models.user import User
from app.schemas.ingredients import StrictSchema
from app.schemas.recipe_source import SourceRead, SourceReferenceInput, SourceReferenceRead
from app.services.recipe_sources import discovery_plan, read_reference, remove_reference, source_read, write_reference
from app.services.deepseek_discovery import discover_recipes
from app.services.deepseek_provider import DeepSeekProvider

router = APIRouter()


class DiscoveryPlanInput(StrictSchema):
    query: str = Field(min_length=1, max_length=80)
    allow_broader_web: bool = False
    include_reviewed_general: bool = False


class DiscoveryInput(StrictSchema):
    query: str = Field(min_length=1, max_length=80)
    allow_broader_web: StrictBool = False
    max_results: int = Field(default=10, strict=True, ge=1, le=20)


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
