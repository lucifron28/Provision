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
        from sqlalchemy import inspect
        inspector = inspect(bind)

        # Adjust inventory_batches -> products foreign key
        for fk in inspector.get_foreign_keys('inventory_batches'):
            if fk.get('referred_table') == 'products':
                fk_name = fk.get('name')
                if fk_name:
                    op.drop_constraint(fk_name, 'inventory_batches', type_='foreignkey')
        op.create_foreign_key(
            'fk_inventory_batches_product_id',
            'inventory_batches',
            'products',
            ['product_id'],
            ['id'],
            ondelete='RESTRICT',
        )

        # Adjust inventory_events -> inventory_batches foreign key
        for fk in inspector.get_foreign_keys('inventory_events'):
            if fk.get('referred_table') == 'inventory_batches':
                fk_name = fk.get('name')
                if fk_name:
                    op.drop_constraint(fk_name, 'inventory_events', type_='foreignkey')
        op.create_foreign_key(
            'fk_inventory_events_batch_id',
            'inventory_events',
            'inventory_batches',
            ['batch_id'],
            ['id'],
            ondelete='RESTRICT',
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        from sqlalchemy import inspect
        inspector = inspect(bind)

        for fk in inspector.get_foreign_keys('inventory_events'):
            if fk.get('referred_table') == 'inventory_batches':
                fk_name = fk.get('name')
                if fk_name:
                    op.drop_constraint(fk_name, 'inventory_events', type_='foreignkey')
        op.create_foreign_key(
            'fk_inventory_events_batch_id',
            'inventory_events',
            'inventory_batches',
            ['batch_id'],
            ['id'],
            ondelete='CASCADE',
        )

        for fk in inspector.get_foreign_keys('inventory_batches'):
            if fk.get('referred_table') == 'products':
                fk_name = fk.get('name')
                if fk_name:
                    op.drop_constraint(fk_name, 'inventory_batches', type_='foreignkey')
        op.create_foreign_key(
            'fk_inventory_batches_product_id',
            'inventory_batches',
            'products',
            ['product_id'],
            ['id'],
            ondelete='CASCADE',
        )
