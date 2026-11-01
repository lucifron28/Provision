from typing import Annotated, Literal
from pydantic import Field, StringConstraints

from app.schemas.ingredients import StrictSchema

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class RecipePreviewRequest(StrictSchema):
    url: LongText
    allow_broader_web: bool = False


class ExtractedRecipeRead(StrictSchema):
    title: Text
    description: Text | None = None
    image_url: LongText | None = None
    ingredients: list[Text] = Field(min_length=1, max_length=150)
    instructions: list[Text] = Field(min_length=1, max_length=150)
    servings: Text | None = None
    prep_time: Text | None = None
    cook_time: Text | None = None
    total_time: Text | None = None
    cuisine: Text | None = None
    category: Text | None = None
    author: Text | None = None
    source_url: LongText
    publisher_name: Text
    source_tier: Literal["filipino_priority", "reviewed_general", "broad_web"] = "filipino_priority"
    untrusted_content: Literal[True] = True
