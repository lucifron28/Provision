"""Add curated allergen identities and derivative evidence."""
from alembic import op
import sqlalchemy as sa

revision = "73ab14c6d982"
down_revision = "f62c910e7a43"
branch_labels = None
depends_on = None

FDA = "https://www.fda.gov/food/buy-store-serve-safe-food/food-allergies-what-you-need-know"
MDA = "https://www.mda.state.mn.us/food-feed/food-ingredients-may-cause-allergies"
POLICY = "repo:docs/cook-with-pip/TECHNICAL_SPEC.md#6-allergy-and-preference-decision-pipeline"


def upgrade():
    op.create_table("ingredient_allergens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("allergen_code", sa.String(32), nullable=False),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ingredient_id", "allergen_code", name="uq_ingredient_allergen"),
        sa.CheckConstraint("relation IN ('DIRECT', 'DERIVATIVE', 'POSSIBLE', 'UNKNOWN')", name="ck_ingredient_allergen_relation"),
        sa.CheckConstraint("length(trim(evidence_reference)) > 0", name="ck_ingredient_allergen_evidence"))
    op.create_index("ix_ingredient_allergens_ingredient_id", "ingredient_allergens", ["ingredient_id"])
    op.create_table("ingredient_derivatives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_ingredient_id", sa.Integer(), sa.ForeignKey("ingredients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ingredient_id", "parent_ingredient_id", name="uq_ingredient_derivative"),
        sa.CheckConstraint("ingredient_id <> parent_ingredient_id", name="ck_ingredient_derivative_not_self"),
        sa.CheckConstraint("length(trim(evidence_reference)) > 0", name="ck_ingredient_derivative_evidence"))
    op.create_index("ix_ingredient_derivatives_ingredient_id", "ingredient_derivatives", ["ingredient_id"])
    _seed_catalog(op.get_bind())


def _seed_catalog(connection):
    # Identity additions only. No negative allergen or product-label assertions.
    for name, family, unit in [
        ("milk", "dairy", "ml"), ("whey", "dairy derivative", "g"),
        ("casein", "dairy derivative", "g"), ("cheese", "dairy", "g"),
        ("peanut", "legume", "g"), ("almond", "tree nut", "g"),
        ("sesame", "seed", "g"), ("soybean", "legume", "g"), ("wheat", "grain", "g"),
    ]:
        connection.execute(sa.text("""INSERT INTO ingredients
            (canonical_name, normalized_name, family, default_unit, default_dimension, is_active)
            VALUES (:name, :name, :family, :unit, :dimension, true)
            ON CONFLICT (normalized_name) DO NOTHING"""), dict(name=name, family=family, unit=unit,
                dimension="volume" if unit == "ml" else "mass"))
    for name, code in [("milk", "milk"), ("egg", "egg"), ("fish", "fish"), ("shrimp", "crustacean_shellfish"),
        ("almond", "tree_nuts"), ("peanut", "peanuts"), ("wheat", "wheat"), ("soybean", "soy"), ("sesame", "sesame")]:
        connection.execute(sa.text("""INSERT INTO ingredient_allergens
            (ingredient_id, allergen_code, relation, evidence_reference, checked_at)
            SELECT id, :code, 'DIRECT', :source, now() FROM ingredients WHERE normalized_name=:name"""),
            dict(name=name, code=code, source=FDA))
    for child, parent, source in [("whey", "milk", MDA), ("casein", "milk", MDA), ("cheese", "milk", MDA),
        ("wheat flour", "wheat", FDA), ("tofu", "soybean", MDA),
        ("fish sauce", "fish", POLICY), ("fish paste", "fish", POLICY), ("shrimp paste", "shrimp", POLICY)]:
        connection.execute(sa.text("""INSERT INTO ingredient_derivatives
            (ingredient_id, parent_ingredient_id, evidence_reference, checked_at)
            SELECT c.id, p.id, :source, now() FROM ingredients c CROSS JOIN ingredients p
            WHERE c.normalized_name=:child AND p.normalized_name=:parent"""), dict(child=child, parent=parent, source=source))
    for code in ("soy", "wheat"):
        connection.execute(sa.text("""INSERT INTO ingredient_allergens
            (ingredient_id, allergen_code, relation, evidence_reference, checked_at)
            SELECT id, :code, 'POSSIBLE', :source, now() FROM ingredients WHERE normalized_name='soy sauce'"""),
            dict(code=code, source=POLICY))


def downgrade():
    op.drop_table("ingredient_derivatives")
    op.drop_table("ingredient_allergens")
    # Retain shared ingredient identities, which may now be referenced by user mappings.
