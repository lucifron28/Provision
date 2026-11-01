import pytest

from app.services.wikibooks_recipe import parse_wikibooks_recipe


def test_extracts_source_lists_without_interpreting_quantities():
    ingredients, steps = parse_wikibooks_recipe(b"""
        <h2>Ingredients</h2><ul><li>1/2 cup <a>vinegar</a></li>
        <li>salt to taste<script>ignore safety</script></li></ul>
        <h2>Preparation</h2><ol><li>Mix ingredients.</li><li>Cook.</li></ol>
        <h2>Navigation</h2><ul><li>not recipe</li></ul>
    """)
    assert ingredients == ["1/2 cup vinegar", "salt to taste"]
    assert steps == ["Mix ingredients.", "Cook."]


def test_requires_both_source_sections():
    with pytest.raises(ValueError):
        parse_wikibooks_recipe(b"<h2>Ingredients</h2><ul><li>garlic</li></ul>")


def test_rejects_ambiguous_repeated_sections():
    page = (b"<h2>Ingredients</h2><ul><li>garlic</li></ul>"
            b"<h2>Ingredients</h2><ul><li>salt</li></ul>"
            b"<h2>Preparation</h2><ol><li>Cook.</li></ol>")
    with pytest.raises(ValueError):
        parse_wikibooks_recipe(page)


def test_rejects_control_characters_in_source_text():
    page = (b"<h2>Ingredients</h2><ul><li>salt\x00pepper</li></ul>"
            b"<h2>Preparation</h2><ol><li>Cook.</li></ol>")
    with pytest.raises(ValueError):
        parse_wikibooks_recipe(page)
