from sqlalchemy import func, select
from db import async_session_maker
from models import IngredientCatalog, IngredientCategory, RecipeCategory
from seed import main as run_seed


async def test_seed_script_idempotency():
    # First launch
    await run_seed()

    async with async_session_maker() as session:
        cat_count_1 = (await session.execute(select(func.count(RecipeCategory.id)))).scalar()
        ing_cat_count_1 = (await session.execute(select(func.count(IngredientCategory.id)))).scalar()
        ing_count_1 = (await session.execute(select(func.count(IngredientCatalog.id)))).scalar()

    assert cat_count_1 > 0
    assert ing_cat_count_1 > 0
    assert ing_count_1 > 0

    # Rerun (checking ON CONFLICT DO NOTHING idempotency)
    await run_seed()

    async with async_session_maker() as session:
        cat_count_2 = (await session.execute(select(func.count(RecipeCategory.id)))).scalar()
        ing_cat_count_2 = (await session.execute(select(func.count(IngredientCategory.id)))).scalar()
        ing_count_2 = (await session.execute(select(func.count(IngredientCatalog.id)))).scalar()

    assert cat_count_1 == cat_count_2
    assert ing_cat_count_1 == ing_cat_count_2
    assert ing_count_1 == ing_count_2
