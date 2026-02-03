"""init schema

Revision ID: 0001
Revises: 
Create Date: 2026-02-03
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('departments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('departments.id')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    op.create_table('contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id'), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('is_archived', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    op.create_table('phones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('number', sa.String(50), nullable=False),
        sa.Column('note', sa.String(255)),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('type', 'number', name='uq_phone_type_number')
    )

    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('login', sa.String(50), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(10), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now())
    )

    op.create_table('banners',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('side', sa.String(10), unique=True, nullable=False),
        sa.Column('image_path', sa.String(255), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'))
    )

    op.create_table('settings',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value', sa.String(255), nullable=False)
    )

    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity', sa.String(100), nullable=False),
        sa.Column('entity_id', sa.Integer()),
        sa.Column('diff_json', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('ip', sa.String(50))
    )

    op.create_table('contact_phones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id'), nullable=False),
        sa.Column('phone_id', sa.Integer(), sa.ForeignKey('phones.id'), nullable=False),
        sa.Column('label', sa.String(50)),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('contact_id', 'phone_id', name='uq_contact_phone')
    )


def downgrade():
    op.drop_table('contact_phones')
    op.drop_table('audit_log')
    op.drop_table('settings')
    op.drop_table('banners')
    op.drop_table('users')
    op.drop_table('phones')
    op.drop_table('contacts')
    op.drop_table('departments')
