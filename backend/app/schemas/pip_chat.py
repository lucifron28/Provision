"""Bounded request and response shapes for read-only Pip Chat."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.deepseek import DeepSeekTokenUsage
from app.schemas.ingredients import StrictSchema

PIP_CHAT_POLICY_VERSION = "2026-11-14-pip-chat-v2"
PIP_CHAT_ALLERGY_POLICY_VERSION = "2026-11-13-pip-chat-allergy-v1"
PIP_CHAT_NOTICE = (
    "Pip Chat sends your current message and up to eight recent turns to DeepSeek after "
    "redacting email addresses and phone numbers. When relevant, it may also send current "
    "household product names, remaining quantities and expiry dates, your food preferences, "
    "recipe ingredients and instructions only when the recipe's sharing permission allows it, "
    "and titles of household recipes. Allergy labels are sent only when you and every active "
    "household member separately opt in to allergy sharing. It never sends account identifiers, "
    "member names, shopping data, or product-label notes. DeepSeek processes requests under "
    "its own privacy policy. You can revoke consent at any time."
)
PIP_CHAT_SAFETY_NOTICE = (
    "Chat suggestions are not food-safety or inventory checks. Verify allergies, product labels, "
    "expiry, and available quantities in Cook with Pip before acting."
)

ChatText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
ChatReference = Annotated[str, StringConstraints(pattern=r"^[IPAR][1-9][0-9]*$", max_length=8)]


class PipChatHistoryTurn(StrictSchema):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class PipChatResourceContext(StrictSchema):
    kind: Literal["recipe", "product"]
    id: int = Field(gt=0)


class PipChatRequest(StrictSchema):
    message: ChatText
    history: list[PipChatHistoryTurn] = Field(default_factory=list, max_length=8)
    context: PipChatResourceContext | None = None
    recent_recipe_ids: list[int] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def bound_and_order_history(self):
        if sum(len(turn.content) for turn in self.history) + len(self.message) > 4000:
            raise ValueError("Chat conversation exceeds the maximum size")
        for index, turn in enumerate(self.history):
            expected = "user" if index % 2 == 0 else "assistant"
            if turn.role != expected:
                raise ValueError("Chat history must contain alternating user and assistant turns")
        if self.history and self.history[-1].role != "assistant":
            raise ValueError("Chat history must end with an assistant turn")
        if any(recipe_id <= 0 for recipe_id in self.recent_recipe_ids):
            raise ValueError("Recent recipe identifiers must be positive")
        if len(self.recent_recipe_ids) != len(set(self.recent_recipe_ids)):
            raise ValueError("Recent recipe identifiers must be unique")
        if self.context and self.context.kind == "recipe" and self.context.id in self.recent_recipe_ids:
            raise ValueError("The selected recipe must not be repeated as recent context")
        return self


class PipChatModelAction(StrictSchema):
    kind: Literal["open_recipe", "open_shopping_preview"]
    reference: ChatReference


class PipChatModelResponse(StrictSchema):
    reply: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
    language: Literal["english", "filipino", "taglish"]
    fact_refs: list[ChatReference] = Field(default_factory=list, max_length=8)
    actions: list[PipChatModelAction] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def references_are_unique(self):
        if len(self.fact_refs) != len(set(self.fact_refs)):
            raise ValueError("Fact references must be unique")
        action_refs = [(action.kind, action.reference) for action in self.actions]
        if len(action_refs) != len(set(action_refs)):
            raise ValueError("Actions must be unique")
        return self


class PipChatFact(StrictSchema):
    reference: ChatReference
    kind: Literal["inventory", "preference", "allergy", "recipe"]
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
    detail: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class PipChatAction(StrictSchema):
    kind: Literal["open_recipe", "open_shopping_preview"]
    reference: ChatReference
    recipe_id: int = Field(gt=0)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PipChatRecipeCard(StrictSchema):
    reference: ChatReference
    recipe_id: int = Field(gt=0)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    cuisine: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    availability_status: Literal["full", "partial", "missing", "unknown"]
    missing_ingredient_count: int = Field(ge=0, le=200)
    safety_decision: Literal["eligible", "blocked", "review_required"]
    safety_reasons: list[Annotated[str, StringConstraints(max_length=100)]] = Field(default_factory=list, max_length=30)


class PipChatRead(StrictSchema):
    reply: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
    language: Literal["english", "filipino", "taglish"]
    facts: list[PipChatFact] = Field(default_factory=list, max_length=8)
    actions: list[PipChatAction] = Field(default_factory=list, max_length=3)
    recipe_cards: list[PipChatRecipeCard] = Field(default_factory=list, max_length=3)
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    usage: DeepSeekTokenUsage
    local_guidance: bool = False
    safety_notice: str = PIP_CHAT_SAFETY_NOTICE


class PipChatConsentUpdate(StrictSchema):
    purpose: Literal["pip_chat_v1", "pip_chat_allergies_v1"]
    policy_version: Literal[
        "2026-11-14-pip-chat-v2",
        "2026-11-13-pip-chat-allergy-v1",
    ]
    granted: bool

    @model_validator(mode="after")
    def purpose_matches_policy(self):
        expected = {
            "pip_chat_v1": PIP_CHAT_POLICY_VERSION,
            "pip_chat_allergies_v1": PIP_CHAT_ALLERGY_POLICY_VERSION,
        }[self.purpose]
        if self.policy_version != expected:
            raise ValueError("The current consent policy is required for this purpose")
        return self


class PipChatConsentRead(StrictSchema):
    chat_granted: bool = False
    all_active_members_chat_granted: bool = False
    allergy_sharing_granted: bool = False
    all_active_members_allergy_sharing_granted: bool = False
    provider_enabled: bool = False
    chat_policy_version: str = PIP_CHAT_POLICY_VERSION
    allergy_policy_version: str = PIP_CHAT_ALLERGY_POLICY_VERSION
    notice: str = PIP_CHAT_NOTICE
