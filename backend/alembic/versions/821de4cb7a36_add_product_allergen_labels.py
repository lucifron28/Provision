"""Record household label reviews against exact product and mapping versions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "821de4cb7a36"
down_revision = "73ab14c6d982"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("product_allergen_labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("product_fingerprint", sa.String(64), nullable=False),
        sa.Column("declared_allergens", JSONB(), nullable=False),
        sa.Column("possible_allergens", JSONB(), nullable=False),
        sa.Column("custom_allergens", JSONB(), nullable=False),
        sa.Column("composition_known", sa.Boolean(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["household_id", "product_id", "mapping_version"],
            ["product_ingredient_mappings.household_id", "product_ingredient_mappings.product_id", "product_ingredient_mappings.version"],
            name="fk_product_allergen_label_mapping", ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "product_id", "revision", name="uq_product_allergen_label_revision"),
        sa.CheckConstraint("revision > 0", name="ck_product_allergen_label_revision"),
        sa.CheckConstraint("length(trim(source_reference)) > 0", name="ck_product_allergen_label_source"))
    op.create_index("uq_product_allergen_label_current", "product_allergen_labels", ["household_id", "product_id"],
        unique=True, postgresql_where=sa.text("is_current IS TRUE"))


def downgrade():
    op.drop_table("product_allergen_labels")
