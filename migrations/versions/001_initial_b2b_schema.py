"""Initial B2B schema with UUID primary keys.

Revision ID: 001
Revises:
Create Date: 2026-07-30

All entity identifiers (id, seller_id, category_id, product_id, sku_id, …)
are UUID. Numeric fields (price, quantity, ordering) remain Integer.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_categories_id", "categories", ["id"])
    op.create_index("ix_categories_slug", "categories", ["slug"])

    op.create_table(
        "product_blocking_reasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    productstatus = postgresql.ENUM(
        "CREATED", "ON_MODERATION", "MODERATED", "BLOCKED", "HARD_BLOCKED",
        name="productstatus", create_type=True,
    )
    productstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "CREATED", "ON_MODERATION", "MODERATED", "BLOCKED", "HARD_BLOCKED",
                name="productstatus", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("blocking_reason_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("blocking_comment", sa.Text(), nullable=True),
        sa.Column("field_reports", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["blocking_reason_id"], ["product_blocking_reasons.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_id", "products", ["id"])
    op.create_index("ix_products_seller_id", "products", ["seller_id"])

    op.create_table(
        "product_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=True, server_default="0"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_images_id", "product_images", ["id"])
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    op.create_table(
        "product_characteristics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_characteristics_id", "product_characteristics", ["id"])
    op.create_index("ix_product_characteristics_product_id", "product_characteristics", ["product_id"])

    op.create_table(
        "skus",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("cost_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("active_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku_code"),
    )
    op.create_index("ix_skus_id", "skus", ["id"])
    op.create_index("ix_skus_sku_code", "skus", ["sku_code"])
    op.create_index("ix_skus_product_id", "skus", ["product_id"])

    op.create_table(
        "sku_characteristics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sku_characteristics_id", "sku_characteristics", ["id"])
    op.create_index("ix_sku_characteristics_sku_id", "sku_characteristics", ["sku_id"])

    invoicestatus = postgresql.ENUM(
        "CREATED", "DRAFT", "SUBMITTED", "ACCEPTED", "REJECTED",
        name="invoicestatus", create_type=True,
    )
    invoicestatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "CREATED", "DRAFT", "SUBMITTED", "ACCEPTED", "REJECTED",
                name="invoicestatus", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("total_amount", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoices_id", "invoices", ["id"])
    op.create_index("ix_invoices_seller_id", "invoices", ["seller_id"])

    op.create_table(
        "invoice_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoice_items_id", "invoice_items", ["id"])
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])

    op.create_foreign_key(
        "fk_categories_parent", "categories", "categories", ["parent_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_categories_parent", "categories", type_="foreignkey")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    op.drop_table("sku_characteristics")
    op.drop_table("skus")
    op.drop_table("product_characteristics")
    op.drop_table("product_images")
    op.drop_table("products")
    op.drop_table("product_blocking_reasons")
    op.drop_table("categories")
    op.execute("DROP TYPE IF EXISTS productstatus")
    op.execute("DROP TYPE IF EXISTS invoicestatus")
