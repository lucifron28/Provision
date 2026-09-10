"""domain integrity adjustments

Revision ID: 5026a110bcf6
Revises: 5472b1b9d375
Create Date: 2026-09-04 00:01:58.131274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5026a110bcf6'
down_revision: Union[str, Sequence[str], None] = '5472b1b9d375'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        with op.batch_alter_table('inventory_batches', schema=None) as batch_op:
            batch_op.drop_constraint('fk_inventory_batches_product_id', type_='foreignkey')
            batch_op.create_foreign_key('fk_inventory_batches_product_id', 'products', ['product_id'], ['id'], ondelete='RESTRICT')

        with op.batch_alter_table('inventory_events', schema=None) as batch_op:
            batch_op.drop_constraint('fk_inventory_events_batch_id', type_='foreignkey')
            batch_op.create_foreign_key('fk_inventory_events_batch_id', 'inventory_batches', ['batch_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        with op.batch_alter_table('inventory_events', schema=None) as batch_op:
            batch_op.drop_constraint('fk_inventory_events_batch_id', type_='foreignkey')
            batch_op.create_foreign_key('fk_inventory_events_batch_id', 'inventory_batches', ['batch_id'], ['id'], ondelete='CASCADE')

        with op.batch_alter_table('inventory_batches', schema=None) as batch_op:
            batch_op.drop_constraint('fk_inventory_batches_product_id', type_='foreignkey')
            batch_op.create_foreign_key('fk_inventory_batches_product_id', 'products', ['product_id'], ['id'], ondelete='CASCADE')
