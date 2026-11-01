import pytest

from app.services.recipe_extractor import extract_recipe_from_html


SAMPLE_PANLASANG_HTML = """
<!DOCTYPE html>
<html lang="en-US">
<head>
<title>Classic Pork Adobo Recipe - Panlasang Pinoy</title>
<meta property="og:title" content="Classic Pork Adobo" />
<meta property="og:image" content="https://panlasangpinoy.com/wp-content/uploads/2021/04/pork-adobo-og.jpg" />
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebPage",
      "@id": "https://panlasangpinoy.com/pork-adobo/#webpage",
      "name": "Pork Adobo Recipe"
    },
    {
      "@type": "Recipe",
      "@id": "https://panlasangpinoy.com/pork-adobo/#recipe",
      "name": "Classic Pork Adobo",
      "description": "Traditional Filipino pork adobo simmered in soy sauce, vinegar, and garlic.",
      "image": [
        "https://panlasangpinoy.com/wp-content/uploads/2021/04/pork-adobo-1x1.jpg",
        "https://panlasangpinoy.com/wp-content/uploads/2021/04/pork-adobo-4x3.jpg"
      ],
      "author": {
        "@type": "Person",
        "name": "Vanjo Merano"
      },
      "prepTime": "PT10M",
      "cookTime": "PT45M",
      "totalTime": "PT55M",
      "recipeYield": ["4 servings"],
      "recipeCategory": ["Main Course"],
      "recipeCuisine": ["Filipino"],
      "recipeIngredient": [
        "2 lbs pork belly sliced into cubes",
        "1/2 cup soy sauce",
        "1/3 cup white vinegar",
        "5 cloves garlic crushed",
        "1 piece bay leaf",
        "1 tsp whole peppercorn",
        "1 cup water",
        "1 tbsp brown sugar"
      ],
      "recipeInstructions": [
        {
          "@type": "HowToStep",
          "text": "Combine pork belly, soy sauce, and garlic in a bowl. Marinate for at least 30 minutes."
        },
        {
          "@type": "HowToStep",
          "text": "Heat a pot and sear the marinated pork until browned on all sides."
        },
        {
          "@type": "HowToStep",
          "text": "Pour in the marinade, water, bay leaf, and peppercorn. Bring to a boil."
        },
        {
          "@type": "HowToStep",
          "text": "Lower heat, cover, and simmer for 40 minutes until pork is tender."
        },
        {
          "@type": "HowToStep",
          "text": "Pour in vinegar and sugar. Simmer uncovered for 10 minutes until sauce thickens."
        }
      ]
    }
  ]
}
</script>
</head>
<body><h1>Classic Pork Adobo</h1></body>
</html>
"""


SAMPLE_KAWALING_HTML = """
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Recipe",
  "name": "Chicken Tinola",
  "description": "Comforting ginger chicken soup with green papaya and chili leaves.",
  "image": "https://www.kawalingpinoy.com/wp-content/uploads/2019/10/chicken-tinola.jpg",
  "author": "Lalaine Manalo",
  "prepTime": "PT15M",
  "cookTime": "PT35M",
  "recipeYield": 6,
  "recipeCategory": "Soup",
  "recipeCuisine": "Filipino",
  "recipeIngredient": [
    "2 lbs chicken cut into serving pieces",
    "2 tbsp cooking oil",
    "1 medium onion sliced",
    "4 cloves garlic minced",
    "2 thumb-sized ginger julienned",
    "2 tbsp fish sauce",
    "5 cups rice water",
    "1 small green papaya peeled and wedged",
    "1 cup chili leaves"
  ],
  "recipeInstructions": [
    {
      "@type": "HowToSection",
      "name": "Preparation",
      "itemListElement": [
        {
          "@type": "HowToStep",
          "text": "In a pot, heat oil over medium heat. Sauté onion, garlic, and ginger until fragrant."
        },
        {
          "@type": "HowToStep",
          "text": "Add chicken pieces and cook until lightly browned."
        }
      ]
    },
    {
      "@type": "HowToSection",
      "name": "Simmering",
      "itemListElement": [
        {
          "@type": "HowToStep",
          "text": "Add fish sauce and stir for 2 minutes. Pour in rice water and bring to a boil."
        },
        {
          "@type": "HowToStep",
          "text": "Lower heat, cover, and simmer for 20 minutes until chicken is tender."
        },
        {
          "@type": "HowToStep",
          "text": "Add green papaya and cook for 5 minutes. Stir in chili leaves and turn off heat."
        }
      ]
    }
  ]
}
</script>
</head>
<body><h1>Chicken Tinola</h1></body>
</html>
"""


def test_extract_panlasang_recipe_with_image_and_instructions():
    recipe = extract_recipe_from_html(
        SAMPLE_PANLASANG_HTML,
        source_url="https://panlasangpinoy.com/pork-adobo/",
        publisher_name="Panlasang Pinoy",
        source_tier="filipino_priority",
    )

    assert recipe.title == "Classic Pork Adobo"
    assert "Traditional Filipino pork adobo" in (recipe.description or "")
    assert recipe.image_url == "https://panlasangpinoy.com/wp-content/uploads/2021/04/pork-adobo-1x1.jpg"
    assert recipe.author == "Vanjo Merano"
    assert len(recipe.ingredients) == 8
    assert recipe.ingredients[0] == "2 lbs pork belly sliced into cubes"
    assert len(recipe.instructions) == 5
    assert "Marinate for at least 30 minutes" in recipe.instructions[0]
    assert recipe.servings == "4 servings"
    assert recipe.prep_time == "10m"
    assert recipe.cook_time == "45m"
    assert recipe.total_time == "55m"
    assert recipe.cuisine == "Filipino"
    assert recipe.category == "Main Course"
    assert recipe.source_url == "https://panlasangpinoy.com/pork-adobo/"
    assert recipe.publisher_name == "Panlasang Pinoy"
    assert recipe.source_tier == "filipino_priority"
    assert recipe.untrusted_content is True


def test_extract_kawaling_recipe_with_sections_and_single_image():
    recipe = extract_recipe_from_html(
        SAMPLE_KAWALING_HTML,
        source_url="https://www.kawalingpinoy.com/chicken-tinola/",
        publisher_name="Kawaling Pinoy",
        source_tier="filipino_priority",
    )

    assert recipe.title == "Chicken Tinola"
    assert recipe.image_url == "https://www.kawalingpinoy.com/wp-content/uploads/2019/10/chicken-tinola.jpg"
    assert recipe.author == "Lalaine Manalo"
    assert len(recipe.ingredients) == 9
    assert len(recipe.instructions) == 5
    assert recipe.servings == "6"
    assert recipe.prep_time == "15m"
    assert recipe.cook_time == "35m"


def test_extract_opengraph_image_fallback():
    html_without_jsonld_image = """
    <html><head>
    <meta property="og:image" content="https://example.com/fallback.jpg" />
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Sinigang na Baboy",
      "recipeIngredient": ["1 lb pork", "tamarind soup base"],
      "recipeInstructions": ["Boil pork in water", "Add tamarind and vegetables"]
    }
    </script>
    </head></html>
    """
    recipe = extract_recipe_from_html(
        html_without_jsonld_image,
        source_url="https://panlasangpinoy.com/sinigang/",
        publisher_name="Panlasang Pinoy",
    )

    assert recipe.image_url == "https://example.com/fallback.jpg"
    assert recipe.title == "Sinigang na Baboy"
    assert len(recipe.ingredients) == 2


def test_extract_rejects_unsafe_image_urls():
    html_unsafe_img = """
    <html><head>
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Dish with Unsafe Image",
      "image": "http://insecure.example.com/img.jpg",
      "recipeIngredient": ["1 cup rice"],
      "recipeInstructions": ["Cook rice"]
    }
    </script>
    </head></html>
    """
    recipe = extract_recipe_from_html(
        html_unsafe_img,
        source_url="https://panlasangpinoy.com/dish/",
        publisher_name="Panlasang Pinoy",
    )
    # HTTP image rejected, image_url should be None
    assert recipe.image_url is None


def test_extract_raises_value_error_on_missing_recipe():
    html_no_recipe = "<html><head><title>About Us</title></head><body>No recipe here</body></html>"
    with pytest.raises(ValueError, match="No parseable recipe"):
        extract_recipe_from_html(
            html_no_recipe,
            source_url="https://panlasangpinoy.com/about/",
            publisher_name="Panlasang Pinoy",
        )
