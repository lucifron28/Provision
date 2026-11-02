"""Add curated ingredient taxonomy and household product mappings."""

from typing import Sequence, Union
import unicodedata

from alembic import op
import sqlalchemy as sa


revision: str = "d91e84af0c52"
down_revision: Union[str, Sequence[str], None] = "b83e6a7d4c91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# This is a migration-time snapshot. Do not import the editable application catalog here.
# Frozen copy of ingredient_catalog_v1.py. Keep parity covered by test_ingredients.py.
_CATALOG_V1_SNAPSHOT = (('garlic', 'bawang', 'allium', 'g', ('bawang', 'garlic cloves', 'fresh garlic')),
 ('onion', 'sibuyas', 'allium', 'g', ('sibuyas', 'bulb onion', 'yellow onion')),
 ('ginger', 'luya', 'root', 'g', ('luya', 'fresh ginger')),
 ('egg', 'itlog', 'egg', 'count', ('itlog', 'chicken egg', 'hen egg')),
 ('eggplant', 'talong', 'vegetable', 'g', ('talong', 'aubergine', 'long eggplant')),
 ('water spinach', 'kangkong', 'leafy vegetable', 'g', ('kangkong', 'swamp cabbage')),
 ('fish sauce', 'patis', 'condiment', 'ml', ('patis',)),
 ('soy sauce', 'toyo', 'condiment', 'ml', ('toyo',)),
 ('shrimp paste',
  'bagoong alamang',
  'fermented condiment',
  'g',
  ('bagoong alamang', 'alamang', 'bagoong')),
 ('fish paste',
  'bagoong isda',
  'fermented condiment',
  'g',
  ('bagoong isda', 'fermented fish paste', 'bagoong')),
 ('rice', 'bigas', 'grain', 'g', ('bigas', 'uncooked rice', 'white rice')),
 ('vinegar', 'suka', 'condiment', 'ml', ('suka', 'cane vinegar')),
 ('tomato', 'kamatis', 'fruit vegetable', 'g', ('kamatis',)),
 ('potato', 'patatas', 'root vegetable', 'g', ('patatas',)),
 ('sweet potato', 'kamote', 'root vegetable', 'g', ('kamote',)),
 ('carrot', 'karot', 'root vegetable', 'g', ('karot',)),
 ('cabbage', 'repolyo', 'leafy vegetable', 'g', ('repolyo',)),
 ('bitter melon', 'ampalaya', 'vegetable', 'g', ('ampalaya', 'bitter gourd')),
 ('squash', 'kalabasa', 'vegetable', 'g', ('kalabasa', 'pumpkin')),
 ('okra', 'okra', 'vegetable', 'g', ("lady's finger",)),
 ('yardlong bean', 'sitaw', 'legume', 'g', ('sitaw', 'long bean', 'snake bean')),
 ('mung bean', 'monggo', 'legume', 'g', ('monggo', 'munggo', 'green gram')),
 ('chicken', 'manok', 'poultry', 'g', ('manok', 'chicken meat')),
 ('pork', 'baboy', 'meat', 'g', ('baboy', 'pork meat')),
 ('beef', 'baka', 'meat', 'g', ('baka', 'beef meat')),
 ('fish', 'isda', 'seafood', 'g', ('isda', 'fresh fish')),
 ('shrimp', 'hipon', 'seafood', 'g', ('hipon', 'prawn')),
 ('calamansi', 'kalamansi', 'citrus fruit', 'count', ('kalamansi', 'calamondin')),
 ('banana', 'saging', 'fruit', 'count', ('saging', 'cooking banana')),
 ('coconut milk', 'gata', 'coconut product', 'ml', ('gata',)),
 ('green chili pepper',
  'siling haba',
  'chili pepper',
  'g',
  ('siling haba', 'finger chili', 'long green chili')),
 ("bird's eye chili", 'siling labuyo', 'chili pepper', 'g', ('siling labuyo', 'thai chili')),
 ('black pepper', 'paminta', 'spice', 'g', ('paminta', 'ground black pepper')),
 ('salt', 'asin', 'seasoning', 'g', ('asin', 'table salt')),
 ('sugar', 'asukal', 'sweetener', 'g', ('asukal', 'white sugar')),
 ('corn', 'mais', 'grain', 'g', ('mais', 'maize')),
 ('wheat flour', 'harina', 'grain product', 'g', ('harina', 'all-purpose flour')),
 ('cooking oil', 'mantika', 'cooking fat', 'ml', ('mantika', 'vegetable oil')),
 ('tofu', 'tokwa', 'soy product', 'g', ('tokwa', 'bean curd')),
 ('mushroom', 'kabute', 'fungus', 'g', ('kabute', 'edible mushroom')),
 ('lemongrass', 'tanglad', 'herb', 'g', ('tanglad', 'lemon grass')),
 ('bay leaf', 'dahon ng laurel', 'herb', 'count', ('dahon ng laurel', 'laurel leaf')),
 ('spring onion',
  'dahon ng sibuyas',
  'allium',
  'g',
  ('dahon ng sibuyas', 'scallion', 'green onion')))


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


_DIMENSION_BY_UNIT = {"g": "mass", "kg": "mass", "ml": "volume", "l": "volume", "count": "count"}


def upgrade() -> None:
    op.create_table(
        "ingredients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.Column("filipino_name", sa.String(length=160), nullable=True),
        sa.Column("family", sa.String(length=80), nullable=True),
        sa.Column("default_dimension", sa.String(length=16), nullable=True),
        sa.Column("default_unit", sa.String(length=24), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "default_dimension IS NULL OR default_dimension IN ('mass', 'volume', 'count')",
            name="ck_ingredients_default_dimension",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name", name="uq_ingredients_normalized_name"),
    )

    op.create_table(
        "ingredient_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=180), nullable=False),
        sa.Column("normalized_alias", sa.String(length=180), nullable=False),
        sa.Column("language", sa.String(length=12), nullable=False),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingredient_id", "normalized_alias", "language", name="uq_ingredient_alias_scope"
        ),
    )
    op.create_index("ix_ingredient_aliases_ingredient_id", "ingredient_aliases", ["ingredient_id"])
    op.create_index("ix_ingredient_aliases_normalized_alias", "ingredient_aliases", ["normalized_alias"])

    op.create_table(
        "product_ingredient_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=True),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=False),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("unknown_composition", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_product_ingredient_mapping_version"),
        sa.CheckConstraint("mode IN ('DIRECT', 'COMPOSITE', 'UNKNOWN')", name="ck_product_ingredient_mapping_mode"),
        sa.CheckConstraint(
            "verification_status IN ('UNVERIFIED', 'VERIFIED', 'UNKNOWN')",
            name="ck_product_ingredient_mapping_verification",
        ),
        sa.CheckConstraint(
            "(mode = 'DIRECT' AND ingredient_id IS NOT NULL) OR "
            "(mode IN ('COMPOSITE', 'UNKNOWN') AND ingredient_id IS NULL)",
            name="ck_product_ingredient_mapping_target",
        ),
        sa.CheckConstraint(
            "mode != 'UNKNOWN' OR (verification_status = 'UNKNOWN' AND unknown_composition IS TRUE)",
            name="ck_product_ingredient_mapping_unknown_state",
        ),
        sa.CheckConstraint(
            "verification_status != 'VERIFIED' OR verified_at IS NOT NULL",
            name="ck_product_ingredient_mapping_verified_at",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_product_ingredient_mapping_confidence",
        ),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["household_id", "product_id"], ["products.household_id", "products.id"],
            name="fk_product_ingredient_mappings_household_product", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "product_id", "version", name="uq_product_ingredient_mapping_version"
        ),
        sa.UniqueConstraint("household_id", "id", name="uq_product_ingredient_mapping_household_id"),
    )
    op.create_index("ix_product_ingredient_mappings_household_id", "product_ingredient_mappings", ["household_id"])
    op.create_index("ix_product_ingredient_mappings_product_id", "product_ingredient_mappings", ["product_id"])
    op.create_index("ix_product_ingredient_mappings_ingredient_id", "product_ingredient_mappings", ["ingredient_id"])
    op.create_index(
        "uq_product_ingredient_mapping_current", "product_ingredient_mappings",
        ["household_id", "product_id"], unique=True,
        postgresql_where=sa.text("is_current IS TRUE"),
        sqlite_where=sa.text("is_current = 1"),
    )

    op.create_table(
        "product_ingredient_mapping_targets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["household_id", "product_id", "mapping_version"],
            [
                "product_ingredient_mappings.household_id",
                "product_ingredient_mappings.product_id",
                "product_ingredient_mappings.version",
            ],
            name="fk_product_ingredient_target_mapping", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "product_id", "mapping_version", "ingredient_id",
            name="uq_product_ingredient_mapping_target_scope",
        ),
    )
    op.create_index("ix_product_ingredient_mapping_targets_household_id", "product_ingredient_mapping_targets", ["household_id"])
    op.create_index("ix_product_ingredient_mapping_targets_ingredient_id", "product_ingredient_mapping_targets", ["ingredient_id"])

    op.create_table(
        "product_package_factors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("inventory_unit", sa.String(length=50), nullable=False),
        sa.Column("ingredient_amount", sa.Numeric(14, 6), nullable=False),
        sa.Column("ingredient_unit", sa.String(length=24), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("verified_by_user_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ingredient_amount > 0", name="ck_product_package_factor_amount"),
        sa.ForeignKeyConstraint(
            ["household_id", "product_id", "mapping_version"],
            [
                "product_ingredient_mappings.household_id",
                "product_ingredient_mappings.product_id",
                "product_ingredient_mappings.version",
            ],
            name="fk_product_package_factor_mapping", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "product_id", "mapping_version", "ingredient_id"],
            [
                "product_ingredient_mapping_targets.household_id",
                "product_ingredient_mapping_targets.product_id",
                "product_ingredient_mapping_targets.mapping_version",
                "product_ingredient_mapping_targets.ingredient_id",
            ],
            name="fk_product_package_factor_mapping_target", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredients.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "household_id", "product_id", "mapping_version", "ingredient_id",
            name="uq_product_package_factor_scope",
        ),
    )
    op.create_index("ix_product_package_factors_household_id", "product_package_factors", ["household_id"])
    op.create_index("ix_product_package_factors_ingredient_id", "product_package_factors", ["ingredient_id"])

    ingredients_table = sa.table(
        "ingredients",
        sa.column("id", sa.Integer()),
        sa.column("canonical_name", sa.String()),
        sa.column("normalized_name", sa.String()),
        sa.column("filipino_name", sa.String()),
        sa.column("family", sa.String()),
        sa.column("default_dimension", sa.String()),
        sa.column("default_unit", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    aliases_table = sa.table(
        "ingredient_aliases",
        sa.column("ingredient_id", sa.Integer()),
        sa.column("alias", sa.String()),
        sa.column("normalized_alias", sa.String()),
        sa.column("language", sa.String()),
        sa.column("region", sa.String()),
        sa.column("reviewed_at", sa.DateTime(timezone=True)),
    )

    bind = op.get_bind()
    for canonical, filipino, family, unit, _aliases in _CATALOG_V1_SNAPSHOT:
        bind.execute(
            ingredients_table.insert().values(
                canonical_name=canonical,
                normalized_name=_normalize(canonical),
                filipino_name=filipino,
                family=family,
                default_dimension=_DIMENSION_BY_UNIT[unit],
                default_unit=unit,
                is_active=True,
            )
        )
    ids = dict(
        bind.execute(
            sa.select(ingredients_table.c.normalized_name, ingredients_table.c.id)
        ).all()
    )
    for canonical, filipino, _family, _unit, aliases in _CATALOG_V1_SNAPSHOT:
        seen: set[tuple[str, str]] = set()
        for alias in tuple(dict.fromkeys((filipino, *aliases))):
            normalized = _normalize(alias)
            language = "fil" if normalized == _normalize(filipino) else "und"
            if (normalized, language) in seen:
                continue
            seen.add((normalized, language))
            bind.execute(
                aliases_table.insert().values(
                    ingredient_id=ids[_normalize(canonical)],
                    alias=alias,
                    normalized_alias=normalized,
                    language=language,
                    region="PH" if language == "fil" else None,
                    reviewed_at=sa.func.now(),
                )
            )


def downgrade() -> None:
    op.drop_index("ix_product_package_factors_ingredient_id", table_name="product_package_factors")
    op.drop_index("ix_product_package_factors_household_id", table_name="product_package_factors")
    op.drop_table("product_package_factors")
    op.drop_index("ix_product_ingredient_mapping_targets_ingredient_id", table_name="product_ingredient_mapping_targets")
    op.drop_index("ix_product_ingredient_mapping_targets_household_id", table_name="product_ingredient_mapping_targets")
    op.drop_table("product_ingredient_mapping_targets")
    op.drop_index("uq_product_ingredient_mapping_current", table_name="product_ingredient_mappings")
    op.drop_index("ix_product_ingredient_mappings_ingredient_id", table_name="product_ingredient_mappings")
    op.drop_index("ix_product_ingredient_mappings_product_id", table_name="product_ingredient_mappings")
    op.drop_index("ix_product_ingredient_mappings_household_id", table_name="product_ingredient_mappings")
    op.drop_table("product_ingredient_mappings")
    op.drop_index("ix_ingredient_aliases_normalized_alias", table_name="ingredient_aliases")
    op.drop_index("ix_ingredient_aliases_ingredient_id", table_name="ingredient_aliases")
    op.drop_table("ingredient_aliases")
    op.drop_table("ingredients")
