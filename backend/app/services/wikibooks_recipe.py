"""Extract visible ingredient and preparation lists from Wikibooks HTML.

The result is untrusted source text. This parser does not approve reuse or
interpret ingredient quantities.
"""

from html.parser import HTMLParser


class _RecipeLists(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.heading = None
        self.item = None
        self.list_depth = 0
        self.hidden = 0
        self.ingredients = []
        self.preparation = []
        self.sections_seen = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template"}:
            self.hidden += 1
            return
        if self.hidden:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading = []
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
        elif tag == "li" and self.list_depth and self.section and self.item is None:
            self.item = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"} and self.hidden:
            self.hidden -= 1
            return
        if self.hidden:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.heading is not None:
            title = " ".join("".join(self.heading).split()).casefold()
            if title == "procedure":
                title = "preparation"
            self.section = title if title in {"ingredients", "preparation"} else None
            if self.section:
                self.sections_seen.append(self.section)
            self.heading = None
        elif tag == "li" and self.item is not None:
            value = " ".join("".join(self.item).split())
            if value:
                if self.section not in {"ingredients", "preparation"}:
                    raise ValueError("Invalid recipe section")
                getattr(self, self.section).append(value)
            self.item = None
        elif tag in {"ul", "ol"}:
            self.list_depth = max(0, self.list_depth - 1)

    def handle_data(self, data):
        if not self.hidden:
            if self.heading is not None:
                self.heading.append(data)
            if self.item is not None:
                self.item.append(data)


def parse_wikibooks_recipe(content: bytes) -> tuple[list[str], list[str]]:
    """Return bounded verbatim list text; reject missing or ambiguous sections."""
    if not isinstance(content, bytes) or len(content) > 500_000:
        raise ValueError("Invalid Wikibooks page")
    parser = _RecipeLists()
    parser.feed(content.decode("utf-8", errors="strict"))
    parser.close()
    if parser.sections_seen != ["ingredients", "preparation"] or not parser.ingredients or not parser.preparation:
        raise ValueError("Recipe sections are missing")
    if any(len(items) > 50 or any(len(item) > 500 or any(ord(char) < 32 or ord(char) == 127 for char in item)
                                   for item in items)
           for items in (parser.ingredients, parser.preparation)):
        raise ValueError("Recipe sections exceed limits")
    return parser.ingredients, parser.preparation
