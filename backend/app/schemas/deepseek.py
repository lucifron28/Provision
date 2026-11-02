"""Typed, bounded request and response shapes for the DeepSeek API adapter."""

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ingredients import StrictSchema


class DeepSeekChatMessage(StrictSchema):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=24000)


class DeepSeekChatRequest(StrictSchema):
    messages: list[DeepSeekChatMessage] = Field(min_length=1, max_length=20)
    max_tokens: int = Field(default=512, strict=True, ge=1, le=8192)

    @model_validator(mode="after")
    def bound_prompt_size(self):
        if sum(len(message.content) for message in self.messages) > 200000:
            raise ValueError("Chat prompt exceeds the maximum size")
        return self


class DeepSeekTokenUsage(StrictSchema):
    prompt_tokens: int = Field(strict=True, ge=0)
    completion_tokens: int = Field(strict=True, ge=0)
    total_tokens: int = Field(strict=True, ge=0)
    reasoning_tokens: int | None = Field(default=None, strict=True, ge=0)

    @model_validator(mode="after")
    def token_total_matches(self):
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("Token usage total does not match prompt and completion counts")
        return self


class DeepSeekChatResponse(StrictSchema):
    model: str = Field(min_length=1, max_length=200)
    finish_reason: Literal["stop"]
    json_object: dict[str, Any]
    usage: DeepSeekTokenUsage


class DeepSeekSearchRequest(StrictSchema):
    query: str = Field(min_length=1, max_length=128)
    count: int = Field(default=10, strict=True, ge=1, le=50)
    ori_question: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("query", "ori_question")
    @classmethod
    def trim_nonblank_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Search text cannot be blank")
        return value


class _DeepSeekWireSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DeepSeekSearchResult(_DeepSeekWireSchema):
    rerank_score: float = Field(ge=0, le=3)
    title: str = Field(max_length=1000)
    url: str = Field(max_length=8192)
    snippet: str = Field(max_length=4000)
    summary: str = Field(max_length=8000)
    content: str = Field(default="", max_length=0)
    site_name: str | None = Field(default=None, max_length=500)
    site_icon: str | None = Field(default=None, max_length=8192)
    date: datetime | None = None
    authority: int = Field(ge=-1, le=4)


class DeepSeekSearchResponse(StrictSchema):
    results: list[DeepSeekSearchResult] = Field(max_length=50)


class DeepSeekFetchRequest(StrictSchema):
    url: str = Field(min_length=1, max_length=8192)

    @field_validator("url")
    @classmethod
    def require_http_url_without_credentials(cls, value: str) -> str:
        value = value.strip()
        if any(ord(char) < 0x20 for char in value):
            raise ValueError("Fetch URL is invalid")
        try:
            parts = urlsplit(value)
            valid_host = bool(parts.hostname)
            _ = parts.port
        except ValueError as exc:
            raise ValueError("Fetch URL is invalid") from exc
        if (
            parts.scheme.lower() not in {"http", "https"}
            or not valid_host
            or parts.username is not None
            or parts.password is not None
            or any(char.isspace() for char in parts.netloc)
        ):
            raise ValueError("Fetch URL must be HTTP(S), include a host, and omit credentials")
        return value


class DeepSeekFetchResponse(StrictSchema):
    title: str = Field(max_length=1000)
    content: str = Field(max_length=500000)
