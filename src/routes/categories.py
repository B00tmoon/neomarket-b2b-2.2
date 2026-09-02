from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_db
from src.models.product import Category

router = APIRouter()


@router.get("/categories", response_model=list)
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Получить дерево категорий."""
    result = await db.execute(select(Category).order_by(Category.name))
    categories = result.scalars().all()

    def build_tree(parent_id=None):
        tree = []
        for cat in categories:
            if cat.parent_id == parent_id:
                children = build_tree(cat.id)
                tree.append(
                    {
                        "id": str(cat.id),
                        "name": cat.name,
                        "slug": cat.slug,
                        "parent_id": str(cat.parent_id) if cat.parent_id else None,
                        "children": children,
                    }
                )
        return tree

    return build_tree()


@router.get("/categories/{category_id}", response_model=dict)
async def get_category(category_id: UUID, db: AsyncSession = Depends(get_db)):
    """Получить категорию с дочерними."""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "parent_id": str(category.parent_id) if category.parent_id else None,
    }


@router.post("/categories", response_model=dict, status_code=201)
async def create_category(
    name: str,
    slug: str,
    parent_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Создать категорию."""
    existing = await db.execute(select(Category).where(Category.slug == slug))
    if existing.scalar():
        raise HTTPException(status_code=400, detail="Category slug already exists")

    category = Category(id=uuid.uuid4(), name=name, slug=slug, parent_id=parent_id)
    db.add(category)
    await db.commit()
    await db.refresh(category)

    return {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "parent_id": str(category.parent_id) if category.parent_id else None,
    }
