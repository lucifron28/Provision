"""Add unapproved publisher candidates, review audit and household references."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "aa812f04d937"
down_revision = "9c67ef2b0134"
branch_labels = None
depends_on = None


def upgrade():
    sources = op.create_table("recipe_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_host", sa.String(253), nullable=False, unique=True),
        sa.Column("publisher_name", sa.String(200), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("policy", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision > 0", name="ck_recipe_source_revision"))
    reviews = op.create_table("recipe_source_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("recipe_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(200), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.UniqueConstraint("source_id", "revision", name="uq_recipe_source_review_revision"))
    op.create_table("recipe_source_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("recipe_sources.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("canonical_url", sa.String(2000), nullable=False),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("broader_web_permission", sa.Boolean(), nullable=False),
        sa.Column("linked_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["household_id", "recipe_id"], ["recipes.household_id", "recipes.id"],
            name="fk_recipe_source_reference_household", ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "recipe_id", name="uq_recipe_source_reference_recipe"),
        sa.CheckConstraint("revision > 0", name="ck_recipe_source_reference_revision"))
    for publisher, host in [("Panlasang Pinoy", "panlasangpinoy.com"), ("Kawaling Pinoy", "www.kawalingpinoy.com"),
        ("Yummy.ph", "www.yummy.ph"), ("Ang Sarap", "www.angsarap.net")]:
        policy = dict(review_status="candidate", tier="filipino_priority", enabled=False,
            allowed_hosts=[host], access_mode="search_link_only", disabled_reason="Pending maintainer terms and access review")
        source_id = op.get_bind().execute(sources.insert().values(canonical_host=host, publisher_name=publisher,
            revision=1, policy=policy).returning(sources.c.id)).scalar_one()
        op.get_bind().execute(reviews.insert().values(source_id=source_id, revision=1,
            reviewed_by="Migration candidate seed, not a permission approval", recorded_at=sa.func.now(), snapshot=policy))


def downgrade():
    op.drop_table("recipe_source_references")
    op.drop_table("recipe_source_reviews")
    op.drop_table("recipe_sources")
