"""Server-side safety decisions, independent of provider output and ranking."""

from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.allergens import IngredientAllergen, IngredientDerivative
from app.models.batch import InventoryBatch
from app.models.household import HouseholdMembership
from app.models.ingredient import Ingredient, ProductIngredientMappingTarget
from app.models.product import Product
from app.models.user import User
from app.schemas.food_safety import FoodSafetyRead, FoodSafetyRequest, IngredientSafetyRead
from app.schemas.ingredients import RecipeAvailabilityRequest
from app.services.ingredient_matching import normalize_ingredient_name, resolve_ingredient
from app.services.product_labels import current_label_context
from app.services.preferences import read_profile
from app.services.recipe_availability import calculate_availability

_COMPLEX_FAMILIES = {"condiment", "fermented condiment", "cooking fat", "grain product", "soy product", "dairy derivative"}
_MEAT_NAMES = {"pork", "beef", "chicken"}
_SIMPLE_FAMILIES = {"allium", "chili pepper", "citrus fruit", "egg", "fruit vegetable", "fruit", "fungus",
    "grain", "herb", "leafy vegetable", "legume", "meat", "poultry", "root vegetable", "root", "seafood",
    "seasoning", "seed", "spice", "sweetener", "tree nut", "vegetable", "dairy"}


def _ancestry(start, edges):
    certain, uncertain, problems = set(), set(), set()
    visited = set()
    pending = [(start, True, ())]
    while pending:
        node, verified, path = pending.pop()
        if node in path or len(path) >= 32 or len(visited) >= 2000:
            problems.add("ingredient_derivative_graph_requires_review")
            continue
        if (node, verified) in visited:
            continue
        visited.add((node, verified))
        (certain if verified else uncertain).add(node)
        for edge in edges.get(node, []):
            reviewed = edge.checked_at is not None and bool(edge.evidence_reference.strip())
            if not reviewed:
                problems.add("ingredient_derivative_unreviewed")
            pending.append((edge.parent_ingredient_id, verified and reviewed, path + (node,)))
    return certain, uncertain - certain, problems


def _decision(blocked, review):
    return "blocked" if blocked else "review_required" if review else "eligible"


def _stock_labels(db, household_id, availability, restricted_codes, custom_texts):
    batch_ids = {batch_id for line in availability.requirements for batch_id in line.covered_batch_ids}
    batches = {item.id: item for item in db.scalars(select(InventoryBatch).where(
        InventoryBatch.household_id == household_id, InventoryBatch.id.in_(batch_ids))).all()}
    product_ids = {batch.product_id for batch in batches.values()}
    products = {item.id: item for item in db.scalars(select(Product).where(
        Product.household_id == household_id, Product.id.in_(product_ids))).all()}
    contexts = {}
    for product_id in sorted(product_ids):
        product = products.get(product_id)
        blocked, review, extra_ids = set(), set(), set()
        label, mapping, usable = current_label_context(db, household_id, product) if product else (None, None, False)
        if not usable:
            review.add("product_allergen_label_not_reviewed")
        else:
            extra_ids.update(db.scalars(select(ProductIngredientMappingTarget.ingredient_id).where(
                ProductIngredientMappingTarget.household_id == household_id,
                ProductIngredientMappingTarget.product_id == product_id,
                ProductIngredientMappingTarget.mapping_version == mapping.version)).all())
            if set(label.declared_allergens) & restricted_codes:
                blocked.add("product_label_allergen_conflict")
            if set(label.possible_allergens) & restricted_codes:
                review.add("product_label_possible_allergen")
            for custom in label.custom_allergens:
                if normalize_ingredient_name(custom) in custom_texts:
                    blocked.add("product_label_custom_allergen_conflict")
                resolution = resolve_ingredient(db, display_name=custom)
                if resolution.ingredient:
                    extra_ids.add(resolution.ingredient.id)
                else:
                    review.add("product_label_custom_ingredient_unresolved")
            if not label.composition_known:
                review.add("product_label_composition_unknown")
        contexts[product_id] = (extra_ids, blocked, review, usable and label.composition_known)
    result = {}
    for line in availability.requirements:
        if line.ingredient_id is None:
            continue
        extra_ids, blocked, review, full = result.get(line.ingredient_id, (set(), set(), set(), True))
        full = full and line.status == "full" and bool(line.covered_batch_ids)
        for batch_id in line.covered_batch_ids:
            batch = batches.get(batch_id)
            if batch is None or batch.product_id not in contexts:
                review.add("product_allergen_label_not_reviewed")
                full = False
                continue
            targets, label_blocked, label_review, complete = contexts[batch.product_id]
            extra_ids.update(targets)
            blocked.update(label_blocked)
            review.update(label_review)
            full = full and complete
        result[line.ingredient_id] = (extra_ids, blocked, review, full)
    return result


def evaluate_food_safety(db: Session, household_id: int, request: FoodSafetyRequest) -> FoodSafetyRead:
    member_ids = set(db.scalars(select(HouseholdMembership.user_id).join(User, User.id == HouseholdMembership.user_id)
        .where(HouseholdMembership.household_id == household_id, User.is_active.is_(True))).all())
    diners = set(request.diner_user_ids) if request.diner_user_ids is not None else member_ids
    if not diners or not diners <= member_ids:
        raise HTTPException(403, "Diners must be active members of the selected household")
    profiles = [read_profile(db, household_id, user_id) for user_id in sorted(diners)]
    shared = read_profile(db, household_id, None)
    profiles.append(shared)
    global_review = {"allergy_information_not_provided"} if any(
        profile.allergy_status == "NOT_PROVIDED" for profile in profiles[:-1]) else set()
    declarations = [item for profile in profiles for item in profile.allergies]
    allergen_codes = {item.allergen_code for item in declarations if item.allergen_code}
    custom_ids = set()
    for item in declarations:
        if item.cross_contact_concern:
            global_review.add("cross_contact_requires_review")
        if item.custom_text:
            resolution = resolve_ingredient(db, display_name=item.custom_text)
            if resolution.ingredient is None:
                global_review.add("custom_allergen_unresolved")
            else:
                custom_ids.add(resolution.ingredient.id)
    excluded = {ingredient_id for profile in profiles for ingredient_id in profile.preferences.ingredient_exclusions}
    diets = {diet for profile in profiles for diet in profile.preferences.diet_patterns}
    if "dairy_free" in diets:
        allergen_codes.add("milk")
    if "gluten_free" in diets:
        allergen_codes.add("wheat")
        global_review.add("gluten_free_requires_label_review")
    restricted_codes = set(allergen_codes)
    if "vegetarian" in diets or "vegan" in diets:
        restricted_codes.update({"fish", "crustacean_shellfish"})
    if "vegan" in diets:
        restricted_codes.update({"milk", "egg"})

    requirements = list(request.requirements)
    for substitution in request.substitutions:
        # A caller cannot turn a required ingredient into an optional one while replacing it.
        original = requirements[substitution.requirement_index]
        requirements[substitution.requirement_index] = substitution.replacement.model_copy(update={"required": original.required})
    availability_request = RecipeAvailabilityRequest(recipe_servings=request.recipe_servings,
        servings=request.servings, requirements=requirements)
    availability = calculate_availability(db, household_id, availability_request)
    stock_labels = _stock_labels(db, household_id, availability, restricted_codes,
        {normalize_ingredient_name(item.custom_text) for item in declarations if item.custom_text})

    edges, associations = defaultdict(list), defaultdict(list)
    for edge in db.scalars(select(IngredientDerivative).order_by(IngredientDerivative.id)).all():
        edges[edge.ingredient_id].append(edge)
    for association in db.scalars(select(IngredientAllergen).order_by(IngredientAllergen.id)).all():
        associations[association.ingredient_id].append(association)
    ingredients = {item.id: item for item in db.scalars(select(Ingredient)).all()}

    lines, all_blocked, all_review = [], set(), set(global_review)
    for index, requirement in enumerate(requirements):
        blocked, review = set(), set(global_review)
        resolution = resolve_ingredient(db, ingredient_id=requirement.ingredient_id, display_name=requirement.display_name)
        ingredient = resolution.ingredient
        if ingredient is None:
            review.add("ingredient_unresolved_or_ambiguous")
        else:
            extra_ids, label_blocked, label_review, fully_labeled = stock_labels.get(ingredient.id, (set(), set(), set(), False))
            blocked.update(label_blocked)
            review.update(label_review)
            certain, uncertain = set(), set()
            for root in sorted(extra_ids | {ingredient.id}):
                confirmed, possible, graph_review = _ancestry(root, edges)
                certain.update(confirmed)
                uncertain.update(possible)
                review.update(graph_review)
            uncertain -= certain
            if certain & excluded:
                blocked.add("ingredient_exclusion_conflict")
            if certain & custom_ids:
                blocked.add("custom_allergen_conflict")
            if uncertain & (excluded | custom_ids):
                review.add("possible_ingredient_conflict")
            for node in sorted(certain | uncertain):
                for association in associations.get(node, []):
                    if association.allergen_code not in restricted_codes:
                        continue
                    if association.relation == "POSSIBLE" and fully_labeled:
                        # Exact reviewed package declarations replace generic possibilities.
                        continue
                    if (node in certain and association.checked_at is not None
                            and association.evidence_reference.strip() and association.relation in {"DIRECT", "DERIVATIVE"}):
                        blocked.add("allergen_conflict")
                    else:
                        review.add("possible_or_unreviewed_allergen")
            names = {ingredients[node].normalized_name for node in certain if node in ingredients}
            families = {ingredients[node].family for node in certain if node in ingredients}
            meat = bool(names & _MEAT_NAMES or families & {"meat", "poultry"})
            animal = meat or bool(names & {"fish", "shrimp"} or "seafood" in families)
            if ("no_pork" in diets or "halal" in diets) and "pork" in names:
                blocked.add("dietary_restriction_conflict")
            if "pescatarian" in diets and meat:
                blocked.add("dietary_restriction_conflict")
            if "vegetarian" in diets and animal:
                blocked.add("dietary_restriction_conflict")
            if "vegan" in diets and (animal or names & {"egg", "milk", "honey"} or families & {"dairy", "egg"}):
                blocked.add("dietary_restriction_conflict")
            if "halal" in diets and animal:
                review.add("halal_certification_not_provided")
            unknown_family = any(ingredients[node].family not in _SIMPLE_FAMILIES | _COMPLEX_FAMILIES
                for node in certain if node in ingredients)
            complex_family = any(ingredients[node].family in _COMPLEX_FAMILIES for node in certain if node in ingredients)
            if unknown_family or uncertain or (complex_family and not fully_labeled):
                review.add("ingredient_composition_requires_review")
            if "no_pork" in diets and meat and not names & _MEAT_NAMES:
                review.add("meat_origin_requires_review")
        line = IngredientSafetyRead(requirement_index=index, ingredient_id=ingredient.id if ingredient else None,
            decision=_decision(blocked, review), reasons=sorted(blocked | review))
        lines.append(line)
        all_blocked.update(blocked)
        all_review.update(review)
    return FoodSafetyRead(decision=_decision(all_blocked, all_review), reasons=sorted(all_blocked | all_review),
        ingredients=lines, availability=availability)
