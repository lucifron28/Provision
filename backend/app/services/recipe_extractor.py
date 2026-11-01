"""Structured recipe and photo extraction from HTML (schema.org/Recipe JSON-LD).

Extracts ingredients, instructions, title, duration, servings, and recipe photo
URL from publisher web pages. All output is marked untrusted_content.
"""

from __future__ import annotations

from html import unescape
import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit

from app.schemas.recipe_extraction import ExtractedRecipeRead


_TAG_RE = re.compile(r"<[^>]+>")
_LD_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
_OG_RE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](og:[a-z_]+)[\"'][^>]+content=[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)
_OG_RE_REVERSED = re.compile(
    r"<meta[^>]+content=[\"']([^\"']*)[\"'][^>]+(?:property|name)=[\"'](og:[a-z_]+)[\"']",
    re.IGNORECASE,
)


def _clean_text(value: Any, max_length: int = 500) -> str | None:
    if not value or not isinstance(value, str):
        return None
    unescaped = unescape(value)
    stripped = _TAG_RE.sub(" ", unescaped)
    cleaned = " ".join(stripped.replace("\r", " ").replace("\n", " ").split())
    # Remove control characters
    filtered = "".join(ch for ch in cleaned if ord(ch) >= 32 and ord(ch) != 127)
    return filtered[:max_length].strip() or None


def _format_duration(value: Any) -> str | None:
    cleaned = _clean_text(value, max_length=50)
    if not cleaned:
        return None
    match = re.match(
        r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", cleaned, re.IGNORECASE
    )
    if not match or not any(match.groups()):
        return cleaned
    days, hours, mins, secs = match.groups()
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    if secs:
        parts.append(f"{secs}s")
    return " ".join(parts) if parts else cleaned


def _validate_image_url(url: Any) -> str | None:
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if len(cleaned) > 2000:
        return None
    try:
        parts = urlsplit(cleaned)
    except Exception:
        return None
    if parts.scheme.lower() != "https" or not parts.hostname:
        return None
    # Reject IP literals, userinfo, and non-ascii
    try:
        ipaddress.ip_address(parts.hostname.strip("[]"))
        return None
    except ValueError:
        pass
    if parts.username or parts.password or not parts.hostname.isascii():
        return None
    if any(ord(c) < 33 or ord(c) > 126 for c in parts.hostname):
        return None
    return cleaned


def _extract_image(image_field: Any) -> str | None:
    if isinstance(image_field, str):
        return _validate_image_url(image_field)
    if isinstance(image_field, list):
        for item in image_field:
            extracted = _extract_image(item)
            if extracted:
                return extracted
    if isinstance(image_field, dict):
        url = image_field.get("url") or image_field.get("contentUrl")
        return _validate_image_url(url)
    return None


def _extract_instructions(instructions_field: Any) -> list[str]:
    steps: list[str] = []
    if isinstance(instructions_field, str):
        for line in instructions_field.splitlines():
            cleaned = _clean_text(line, max_length=500)
            if cleaned:
                steps.append(cleaned)
    elif isinstance(instructions_field, list):
        for item in instructions_field:
            if isinstance(item, str):
                cleaned = _clean_text(item, max_length=500)
                if cleaned:
                    steps.append(cleaned)
            elif isinstance(item, dict):
                # Handle HowToSection containing itemListElement
                if item.get("@type") == "HowToSection" and isinstance(
                    item.get("itemListElement"), list
                ):
                    section_steps = _extract_instructions(item["itemListElement"])
                    steps.extend(section_steps)
                else:
                    text = item.get("text") or item.get("name")
                    cleaned = _clean_text(text, max_length=500)
                    if cleaned:
                        steps.append(cleaned)
    return [s for s in steps if len(s) >= 3]


def _find_recipe_nodes(data: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(data, dict):
        type_field = data.get("@type")
        is_recipe = (
            type_field == "Recipe"
            or (isinstance(type_field, list) and "Recipe" in type_field)
        )
        if is_recipe:
            nodes.append(data)
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                nodes.extend(_find_recipe_nodes(item))
    elif isinstance(data, list):
        for item in data:
            nodes.extend(_find_recipe_nodes(item))
    return nodes


def _extract_opengraph(html_text: str) -> dict[str, str]:
    og: dict[str, str] = {}
    for match in _OG_RE.finditer(html_text):
        prop, content = match.group(1).lower(), match.group(2).strip()
        if prop not in og:
            og[prop] = content
    for match in _OG_RE_REVERSED.finditer(html_text):
        content, prop = match.group(1).strip(), match.group(2).lower()
        if prop not in og:
            og[prop] = content
    return og


def extract_recipe_from_html(
    html_content: str | bytes,
    *,
    source_url: str,
    publisher_name: str,
    source_tier: str = "filipino_priority",
) -> ExtractedRecipeRead:
    """Parse recipe metadata, text, and photo from HTML string or bytes.

    Prefers Schema.org Recipe JSON-LD and falls back to OpenGraph metadata.
    Raises ValueError if no recipe with ingredients can be parsed.
    """
    if isinstance(html_content, bytes):
        text = html_content.decode("utf-8", errors="replace")
    else:
        text = html_content

    recipe_node: dict[str, Any] | None = None

    # 1. Parse JSON-LD blocks
    for match in _LD_JSON_RE.finditer(text):
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
        except Exception:
            continue
        found = _find_recipe_nodes(parsed)
        if found:
            recipe_node = found[0]
            break

    og_meta = _extract_opengraph(text)

    if recipe_node is not None:
        title = _clean_text(recipe_node.get("name") or recipe_node.get("headline"))
        description = _clean_text(recipe_node.get("description"), max_length=1000)
        image_url = _extract_image(recipe_node.get("image")) or _validate_image_url(
            og_meta.get("og:image")
        )

        raw_ingredients = recipe_node.get("recipeIngredient") or []
        if isinstance(raw_ingredients, str):
            raw_ingredients = [raw_ingredients]
        ingredients = []
        for ing in raw_ingredients:
            cleaned = _clean_text(ing, max_length=200)
            if cleaned:
                ingredients.append(cleaned)

        instructions = _extract_instructions(recipe_node.get("recipeInstructions"))

        servings = None
        yield_val = recipe_node.get("recipeYield")
        if isinstance(yield_val, list) and yield_val:
            servings = _clean_text(str(yield_val[0]), max_length=50)
        elif yield_val:
            servings = _clean_text(str(yield_val), max_length=50)

        prep_time = _format_duration(recipe_node.get("prepTime"))
        cook_time = _format_duration(recipe_node.get("cookTime"))
        total_time = _format_duration(recipe_node.get("totalTime"))

        cuisine = None
        raw_cuisine = recipe_node.get("recipeCuisine")
        if isinstance(raw_cuisine, list):
            cuisine = ", ".join(filter(None, (_clean_text(c, 50) for c in raw_cuisine)))
        elif raw_cuisine:
            cuisine = _clean_text(raw_cuisine, 100)

        category = None
        raw_cat = recipe_node.get("recipeCategory")
        if isinstance(raw_cat, list):
            category = ", ".join(filter(None, (_clean_text(c, 50) for c in raw_cat)))
        elif raw_cat:
            category = _clean_text(raw_cat, 100)

        author = None
        raw_author = recipe_node.get("author")
        if isinstance(raw_author, dict):
            author = _clean_text(raw_author.get("name"), 100)
        elif isinstance(raw_author, list) and raw_author:
            first = raw_author[0]
            author = _clean_text(first.get("name") if isinstance(first, dict) else str(first), 100)
        elif raw_author:
            author = _clean_text(str(raw_author), 100)

        if not title:
            title = _clean_text(og_meta.get("og:title")) or f"{publisher_name} Recipe"

        if ingredients and instructions:
            return ExtractedRecipeRead(
                title=title,
                description=description,
                image_url=image_url,
                ingredients=ingredients,
                instructions=instructions,
                servings=servings,
                prep_time=prep_time,
                cook_time=cook_time,
                total_time=total_time,
                cuisine=cuisine,
                category=category,
                author=author,
                source_url=source_url,
                publisher_name=publisher_name,
                source_tier=source_tier,
                untrusted_content=True,
            )

    raise ValueError("No parseable recipe with ingredients and instructions found in page content")
