"""Manually curated ingredient identities and Filipino/English search aliases.

Version 1 records generic ingredient identities, using familiar Filipino and
English names as search terms. The initial Filipino pairs follow the project
contract; the remaining terms were curated as generic ingredient vocabulary.
This file contains no publisher recipe text and makes no claims about allergens
or dietary suitability. ``default_unit`` is only the ingredient's canonical
measurement unit. It is not a product-size or package conversion.

Keep this catalog versioned and review identity changes explicitly. Repeated
aliases are retained when ordinary usage is ambiguous, such as ``bagoong`` for
both shrimp paste and fish paste.
"""

from typing import Final, TypedDict


class IngredientCatalogEntry(TypedDict):
    canonical_name: str
    filipino_name: str
    family: str
    default_unit: str
    aliases: tuple[str, ...]


INGREDIENT_CATALOG_V1: Final[tuple[IngredientCatalogEntry, ...]] = (
    {
        "canonical_name": "garlic",
        "filipino_name": "bawang",
        "family": "allium",
        "default_unit": "g",
        "aliases": ("bawang", "garlic cloves", "fresh garlic"),
    },
    {
        "canonical_name": "onion",
        "filipino_name": "sibuyas",
        "family": "allium",
        "default_unit": "g",
        "aliases": ("sibuyas", "bulb onion", "yellow onion"),
    },
    {
        "canonical_name": "ginger",
        "filipino_name": "luya",
        "family": "root",
        "default_unit": "g",
        "aliases": ("luya", "fresh ginger"),
    },
    {
        "canonical_name": "egg",
        "filipino_name": "itlog",
        "family": "egg",
        "default_unit": "count",
        "aliases": ("itlog", "chicken egg", "hen egg"),
    },
    {
        "canonical_name": "eggplant",
        "filipino_name": "talong",
        "family": "vegetable",
        "default_unit": "g",
        "aliases": ("talong", "aubergine", "long eggplant"),
    },
    {
        "canonical_name": "water spinach",
        "filipino_name": "kangkong",
        "family": "leafy vegetable",
        "default_unit": "g",
        "aliases": ("kangkong", "swamp cabbage"),
    },
    {
        "canonical_name": "fish sauce",
        "filipino_name": "patis",
        "family": "condiment",
        "default_unit": "ml",
        "aliases": ("patis",),
    },
    {
        "canonical_name": "soy sauce",
        "filipino_name": "toyo",
        "family": "condiment",
        "default_unit": "ml",
        "aliases": ("toyo",),
    },
    {
        "canonical_name": "shrimp paste",
        "filipino_name": "bagoong alamang",
        "family": "fermented condiment",
        "default_unit": "g",
        "aliases": ("bagoong alamang", "alamang", "bagoong"),
    },
    {
        "canonical_name": "fish paste",
        "filipino_name": "bagoong isda",
        "family": "fermented condiment",
        "default_unit": "g",
        "aliases": ("bagoong isda", "fermented fish paste", "bagoong"),
    },
    {
        "canonical_name": "rice",
        "filipino_name": "bigas",
        "family": "grain",
        "default_unit": "g",
        "aliases": ("bigas", "uncooked rice", "white rice"),
    },
    {
        "canonical_name": "vinegar",
        "filipino_name": "suka",
        "family": "condiment",
        "default_unit": "ml",
        "aliases": ("suka", "cane vinegar"),
    },
    {
        "canonical_name": "tomato",
        "filipino_name": "kamatis",
        "family": "fruit vegetable",
        "default_unit": "g",
        "aliases": ("kamatis",),
    },
    {
        "canonical_name": "potato",
        "filipino_name": "patatas",
        "family": "root vegetable",
        "default_unit": "g",
        "aliases": ("patatas",),
    },
    {
        "canonical_name": "sweet potato",
        "filipino_name": "kamote",
        "family": "root vegetable",
        "default_unit": "g",
        "aliases": ("kamote",),
    },
    {
        "canonical_name": "carrot",
        "filipino_name": "karot",
        "family": "root vegetable",
        "default_unit": "g",
        "aliases": ("karot",),
    },
    {
        "canonical_name": "cabbage",
        "filipino_name": "repolyo",
        "family": "leafy vegetable",
        "default_unit": "g",
        "aliases": ("repolyo",),
    },
    {
        "canonical_name": "bitter melon",
        "filipino_name": "ampalaya",
        "family": "vegetable",
        "default_unit": "g",
        "aliases": ("ampalaya", "bitter gourd"),
    },
    {
        "canonical_name": "squash",
        "filipino_name": "kalabasa",
        "family": "vegetable",
        "default_unit": "g",
        "aliases": ("kalabasa", "pumpkin"),
    },
    {
        "canonical_name": "okra",
        "filipino_name": "okra",
        "family": "vegetable",
        "default_unit": "g",
        "aliases": ("lady's finger",),
    },
    {
        "canonical_name": "yardlong bean",
        "filipino_name": "sitaw",
        "family": "legume",
        "default_unit": "g",
        "aliases": ("sitaw", "long bean", "snake bean"),
    },
    {
        "canonical_name": "mung bean",
        "filipino_name": "monggo",
        "family": "legume",
        "default_unit": "g",
        "aliases": ("monggo", "munggo", "green gram"),
    },
    {
        "canonical_name": "chicken",
        "filipino_name": "manok",
        "family": "poultry",
        "default_unit": "g",
        "aliases": ("manok", "chicken meat"),
    },
    {
        "canonical_name": "pork",
        "filipino_name": "baboy",
        "family": "meat",
        "default_unit": "g",
        "aliases": ("baboy", "pork meat"),
    },
    {
        "canonical_name": "beef",
        "filipino_name": "baka",
        "family": "meat",
        "default_unit": "g",
        "aliases": ("baka", "beef meat"),
    },
    {
        "canonical_name": "fish",
        "filipino_name": "isda",
        "family": "seafood",
        "default_unit": "g",
        "aliases": ("isda", "fresh fish"),
    },
    {
        "canonical_name": "shrimp",
        "filipino_name": "hipon",
        "family": "seafood",
        "default_unit": "g",
        "aliases": ("hipon", "prawn"),
    },
    {
        "canonical_name": "calamansi",
        "filipino_name": "kalamansi",
        "family": "citrus fruit",
        "default_unit": "count",
        "aliases": ("kalamansi", "calamondin"),
    },
    {
        "canonical_name": "banana",
        "filipino_name": "saging",
        "family": "fruit",
        "default_unit": "count",
        "aliases": ("saging", "cooking banana"),
    },
    {
        "canonical_name": "coconut milk",
        "filipino_name": "gata",
        "family": "coconut product",
        "default_unit": "ml",
        "aliases": ("gata",),
    },
    {
        "canonical_name": "green chili pepper",
        "filipino_name": "siling haba",
        "family": "chili pepper",
        "default_unit": "g",
        "aliases": ("siling haba", "finger chili", "long green chili"),
    },
    {
        "canonical_name": "bird's eye chili",
        "filipino_name": "siling labuyo",
        "family": "chili pepper",
        "default_unit": "g",
        "aliases": ("siling labuyo", "thai chili"),
    },
    {
        "canonical_name": "black pepper",
        "filipino_name": "paminta",
        "family": "spice",
        "default_unit": "g",
        "aliases": ("paminta", "ground black pepper"),
    },
    {
        "canonical_name": "salt",
        "filipino_name": "asin",
        "family": "seasoning",
        "default_unit": "g",
        "aliases": ("asin", "table salt"),
    },
    {
        "canonical_name": "sugar",
        "filipino_name": "asukal",
        "family": "sweetener",
        "default_unit": "g",
        "aliases": ("asukal", "white sugar"),
    },
    {
        "canonical_name": "corn",
        "filipino_name": "mais",
        "family": "grain",
        "default_unit": "g",
        "aliases": ("mais", "maize"),
    },
    {
        "canonical_name": "wheat flour",
        "filipino_name": "harina",
        "family": "grain product",
        "default_unit": "g",
        "aliases": ("harina", "all-purpose flour"),
    },
    {
        "canonical_name": "cooking oil",
        "filipino_name": "mantika",
        "family": "cooking fat",
        "default_unit": "ml",
        "aliases": ("mantika", "vegetable oil"),
    },
    {
        "canonical_name": "tofu",
        "filipino_name": "tokwa",
        "family": "soy product",
        "default_unit": "g",
        "aliases": ("tokwa", "bean curd"),
    },
    {
        "canonical_name": "mushroom",
        "filipino_name": "kabute",
        "family": "fungus",
        "default_unit": "g",
        "aliases": ("kabute", "edible mushroom"),
    },
    {
        "canonical_name": "lemongrass",
        "filipino_name": "tanglad",
        "family": "herb",
        "default_unit": "g",
        "aliases": ("tanglad", "lemon grass"),
    },
    {
        "canonical_name": "bay leaf",
        "filipino_name": "dahon ng laurel",
        "family": "herb",
        "default_unit": "count",
        "aliases": ("dahon ng laurel", "laurel leaf"),
    },
    {
        "canonical_name": "spring onion",
        "filipino_name": "dahon ng sibuyas",
        "family": "allium",
        "default_unit": "g",
        "aliases": ("dahon ng sibuyas", "scallion", "green onion"),
    },
)
