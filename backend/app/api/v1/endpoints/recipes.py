from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.recipe import Recipe, SavedRecipe
from app.models.user import User
from app.schemas.recipe import (RecipeEvaluationInput, RecipeEvaluationRead, RecipeRead, RecipeWrite,
    SavedRecipeRead, SaveRecipeInput)
from app.schemas.recommendations import RecommendationInput, RecommendationRead
from app.services.recommendations import recommend_recipes
from app.services.recipes import (archive_recipe, evaluate_recipe, get_recipe, read_recipe, read_revision,
    read_saved, remove_saved, save_recipe, saved_read, write_recipe)

router = APIRouter()


@router.post("/recommendations", response_model=RecommendationRead)
def recommendations(request: RecommendationInput, response: Response,
                    household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return recommend_recipes(db, household_id, user.id, request)


@router.get("/", response_model=list[RecipeRead])
def list_recipes(response: Response, query: str | None = Query(None, max_length=180),
                 limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=100000),
                 household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    statement = select(Recipe).where(Recipe.household_id == household_id, Recipe.is_active.is_(True))
    if query:
        statement = statement.where(Recipe.title.icontains(query, autoescape=True))
    records = db.scalars(statement.order_by(func.lower(Recipe.title), Recipe.id).limit(limit).offset(offset)).all()
    return [read_recipe(db, record) for record in records]


@router.post("/", response_model=RecipeRead, status_code=201)
def create_recipe(request: RecipeWrite, response: Response, household_id: int = Depends(get_current_household_id),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return write_recipe(db, household_id, user.id, request)


@router.get("/saved", response_model=list[SavedRecipeRead])
def list_saved(response: Response, household_id: int = Depends(get_current_household_id),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    rows = db.scalars(select(SavedRecipe).where(SavedRecipe.household_id == household_id,
        SavedRecipe.member_user_id == user.id, SavedRecipe.is_saved.is_(True)).order_by(SavedRecipe.recipe_id)).all()
    return [saved_read(row) for row in rows]


@router.get("/{recipe_id}", response_model=RecipeRead)
def recipe_detail(recipe_id: int, response: Response, household_id: int = Depends(get_current_household_id),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_recipe(db, get_recipe(db, household_id, recipe_id))


@router.put("/{recipe_id}", response_model=RecipeRead)
def update_recipe(recipe_id: int, request: RecipeWrite, response: Response,
                  household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return write_recipe(db, household_id, user.id, request, recipe_id)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, expected_revision: int = Query(ge=1),
                  household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    archive_recipe(db, household_id, user.id, recipe_id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/{recipe_id}/versions/{revision}", response_model=RecipeRead)
def recipe_version(recipe_id: int, revision: int, response: Response,
                   household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_revision(db, household_id, recipe_id, revision)


@router.post("/{recipe_id}/evaluate", response_model=RecipeEvaluationRead)
def recipe_evaluation(recipe_id: int, request: RecipeEvaluationInput, response: Response,
                      household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return evaluate_recipe(db, household_id, recipe_id, request)


@router.get("/{recipe_id}/saved", response_model=SavedRecipeRead)
def saved_detail(recipe_id: int, response: Response, household_id: int = Depends(get_current_household_id),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_saved(db, household_id, user.id, recipe_id)


@router.put("/{recipe_id}/saved", response_model=SavedRecipeRead)
def set_saved(recipe_id: int, request: SaveRecipeInput, response: Response,
              household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return save_recipe(db, household_id, user.id, recipe_id, request)


@router.delete("/{recipe_id}/saved", status_code=204)
def unsave(recipe_id: int, expected_revision: int = Query(ge=1), household_id: int = Depends(get_current_household_id),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    remove_saved(db, household_id, user.id, recipe_id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
