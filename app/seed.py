"""Seed script — populates reference tables with initial data.

Fills:
- recipe_categories  (one category per recipe, e.g. "Salads", "Soups")
- ingredient_categories + ingredients_catalog (grouped ingredient master list)

Safe to run multiple times: uses PostgreSQL's INSERT ... ON CONFLICT DO NOTHING on the
`name` unique constraint, so re-running never creates duplicate rows even if some
categories/ingredients already exist.

Usage:
    docker compose exec api python seed.py
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session_maker
from models import IngredientCatalog, IngredientCategory, RecipeCategory


RECIPE_CATEGORIES = [
    # Salads & Appetizers
    "Salads",
    "Cold Appetizers",
    "Hot Appetizers",
    "Sandwiches & Toast",
    "Burgers & Wraps",
    "Street Food & Tacos",

    # Soups
    "Soups & Broths",
    "Chilled Soups",

    # Main Courses
    "Main Dishes",
    "Meat Dishes",
    "Poultry Dishes",
    "Fish & Seafood",
    "Vegetables & Greens",
    "Mushroom Dishes",
    "Egg Dishes",
    "Cheese & Dairy Dishes",

    # Grains, Pasta & Dumplings
    "Side Dishes & Grains",
    "Pasta & Risotto",
    "Dumplings & Noodles",
    "Sushi, Rolls & Sashimi",
    "Pizza & Flatbreads",

    # Baking & Dough
    "Sweet Baking",
    "Savory Baking",
    "Bread & Artisanal Loaves",
    "Pies, Quiches & Tarts",
    "Pancakes, Crepes & Waffles",
    "Pastries & Savory Pies",

    # Desserts & Sweets
    "Desserts",
    "Cakes & Pastries",
    "Candies & Confectionery",
    "Ice Cream & Frozen Desserts",
    "Jams, Jellies & Preserves",

    # Sauces & Pantry
    "Sauces, Marinades & Dips",
    "Canning & Pickles",
    "Spice Blends & Condiments",

    # Beverages
    "Non-Alcoholic Beverages",
    "Alcoholic Beverages",
    "Cocktails",
    "Tea, Coffee & Hot Drinks",
    "Smoothies, Juices & Lemonades",
]

INGREDIENT_CATEGORIES: dict[str, list[str]] = {
    # Meat, Poultry & Offal
    "Meat & Poultry": [
        "Chicken Breast / Fillet",
        "Chicken Thighs",
        "Chicken Wings",
        "Beef",
        "Veal",
        "Pork",
        "Lamb / Mutton",
        "Turkey",
        "Duck",
        "Goose",
        "Ground Beef",
        "Ground Pork",
        "Ground Pork & Beef Mix",
        "Ground Chicken",
        "Ground Turkey",
        "Bacon",
        "Ham",
        "Prosciutto / Jamón",
        "Cooked Sausage / Bologna",
        "Dry-Cured Sausage / Salami",
        "Sausages / Hot Dogs",
        "Chicken Liver",
        "Beef Liver",
        "Beef Tongue",
    ],
    # Fish & Seafood
    "Fish & Seafood": [
        "Salmon / Atlantic Salmon",
        "Trout",
        "Tuna",
        "Cod",
        "Pollock",
        "Mackerel",
        "Herring",
        "Anchovies",
        "Shrimp / Prawns",
        "Squid / Calamari",
        "Mussels",
        "Octopus",
        "Scallops",
        "Crab Sticks / Crab Meat",
        "Red Caviar",
        "Black Caviar",
        "Tobiko / Masago Caviar",
    ],
    # Vegetables, Mushrooms & Fresh Herbs
    "Vegetables, Mushrooms & Herbs": [
        "Yellow Onion",
        "Green Onions / Scallions",
        "Leek",
        "Red Onion",
        "Shallot",
        "Carrots",
        "Potatoes",
        "Sweet Potatoes / Yams",
        "Tomatoes",
        "Cherry Tomatoes",
        "Sun-Dried Tomatoes",
        "Cucumbers",
        "Garlic",
        "Bell Pepper",
        "Chili Pepper / Jalapeño",
        "Zucchini / Courgette",
        "Eggplant / Aubergine",
        "Artichokes",
        "Green Cabbage",
        "Red Cabbage",
        "Napa / Chinese Cabbage",
        "Cauliflower",
        "Broccoli",
        "Beetroot",
        "Avocado",
        "Asparagus",
        "Celery (Stalk / Root)",
        "Button Mushrooms / Cremini",
        "Porcini / Wild Mushrooms",
        "Oyster Mushrooms",
        "Chanterelles",
        "Truffle (Fresh / Paste / Oil)",
        "Fresh Dill",
        "Fresh Parsley",
        "Fresh Basil",
        "Fresh Cilantro / Coriander",
        "Fresh Spinach",
        "Fresh Mint",
        "Fresh Rosemary",
        "Fresh Thyme",
        "Tarragon",
        "Sorrel",
    ],
    # Salad Greens & Leafy Mixes
    "Salad Greens & Mixes": [
        "Butter / Head Lettuce",
        "Iceberg Lettuce",
        "Romaine Lettuce",
        "Arugula / Rocket",
        "Mâche / Corn Salad",
        "Radicchio",
        "Mixed Salad Greens",
    ],
    # Fruits, Berries, Nuts & Seeds
    "Fruits, Berries, Nuts & Seeds": [
        "Apples",
        "Pears",
        "Bananas",
        "Lemons",
        "Limes",
        "Oranges",
        "Grapefruits",
        "Tangerines / Mandarins",
        "Strawberries",
        "Raspberries",
        "Blueberries",
        "Blackberries",
        "Cherries",
        "Pineapple",
        "Peaches / Nectarines",
        "Plums",
        "Kiwi",
        "Mango",
        "Figs",
        "Raisins / Dried Apricots / Prunes",
        "Walnuts",
        "Almonds",
        "Peanuts",
        "Cashews",
        "Hazelnuts",
        "Pistachios",
        "Pine Nuts",
        "Sesame Seeds (White / Black)",
        "Sunflower Seeds",
        "Pumpkin Seeds",
        "Flaxseeds",
        "Chia Seeds",
    ],
    # Dairy, Ice Cream & Eggs
    "Dairy, Ice Cream & Eggs": [
        "Chicken Eggs",
        "Quail Eggs",
        "Milk",
        "Light Cream (10-20%)",
        "Heavy Cream / Whipping Cream (30-35%)",
        "Butter",
        "Ghee / Clarified Butter",
        "Sour Cream",
        "Cottage Cheese / Farmers Cheese",
        "Plain Yogurt / Greek Yogurt",
        "Kefir / Buttermilk",
        "Sweetened Condensed Milk",
        "Vanilla Ice Cream",
        "Chocolate Ice Cream",
        "Sorbet / Fruit Ice",
    ],
    # Cheese Selection
    "Cheese": [
        "Parmesan / Grana Padano",
        "Hard Cheese (Cheddar, Gouda, Edam)",
        "Semi-Hard Cheese (Swiss, Havarti)",
        "Mozzarella (Fresh / Low Moisture)",
        "Suluguni Cheese",
        "Cheddar Cheese",
        "Cream Cheese",
        "Mascarpone",
        "Ricotta",
        "Feta Cheese",
        "Brynza / Salty White Cheese",
        "Sirtaki / Halloumi Cheese",
        "Blue Cheese (Gorgonzola, Roquefort)",
        "Brie / Camembert",
        "Processed Cheese",
    ],
    # Grains, Legumes, Flour & Pasta
    "Grains, Legumes, Flour & Pasta": [
        "All-Purpose Flour",
        "Rye Flour",
        "Oat / Rice / Corn Flour",
        "Almond Flour",
        "Sushi Rice (Short-Grain)",
        "Long-Grain Rice (Basmati / Jasmine)",
        "Brown / Wild Rice",
        "Buckwheat",
        "Rolled Oats / Oatmeal",
        "Semolina",
        "Bulgur",
        "Couscous",
        "Quinoa",
        "Pasta / Spaghetti / Noodles",
        "Udon Noodles",
        "Soba Noodles",
        "Glass Noodles / Cellophane Noodles",
        "White Beans (Dry / Canned)",
        "Kidney Beans (Dry / Canned)",
        "Green Beans / String Beans",
        "Edamame / Fava Beans",
        "Chickpeas (Dry / Canned)",
        "Lentils (Red / Green)",
        "Peas (Dry / Canned Green Peas)",
        "Cornstarch / Potato Starch",
        "Breadcrumbs / Panko",
    ],
    # Oils
    "Plant Oils": [
        "Sunflower Oil",
        "Extra Virgin Olive Oil",
        "Olive Oil (for cooking)",
        "Sesame Oil",
        "Canola / Rapeseed Oil",
        "Flaxseed Oil",
        "Coconut Oil",
        "Mustard Oil",
        "Walnut Oil",
        "Truffle Oil",
    ],
    # Sauces, Vinegars & Condiments
    "Sauces, Vinegars & Condiments": [
        "Mayonnaise",
        "Ketchup",
        "Tomato Paste",
        "Canned Crushed Tomatoes",
        "Soy Sauce",
        "Teriyaki Sauce",
        "Sriracha Sauce",
        "Tabasco Sauce",
        "Pesto Sauce",
        "Barbecue Sauce (BBQ)",
        "Oyster Sauce",
        "Fish Sauce",
        "Yellow / Yellow Table Mustard",
        "Dijon Mustard",
        "Whole Grain / French Mustard",
        "Prepared Horseradish / Wasabi",
        "White Distilled Vinegar (9%)",
        "Apple Cider Vinegar",
        "Wine Vinegar (White / Red)",
        "Balsamic Vinegar / Balsamic Glaze",
        "Rice Vinegar",
        "Capers",
    ],
    # Spices, Seasonings & Dried Herbs
    "Spices & Seasonings": [
        "Table Salt / Sea Salt",
        "Garlic Salt / Seasoned Salt",
        "Ground Black Pepper",
        "Black Peppercorns",
        "Mixed Peppercorns",
        "Red Chili Powder / Flakes",
        "Sweet Paprika",
        "Smoked Paprika",
        "Garlic Powder / Granules",
        "Turmeric",
        "Curry Powder",
        "Cumin (Jeera)",
        "Ground Coriander / Coriander Seeds",
        "Ground Ginger / Fresh Ginger Root",
        "Ground Nutmeg",
        "Whole Cloves",
        "Ground Cinnamon / Cinnamon Sticks",
        "Star Anise",
        "Cardamom",
        "Saffron",
        "Khmeli-Suneli",
        "Italian / Herbs de Provence Mix",
        "Dried Oregano",
        "Dried Marjoram",
        "Dried Basil",
        "Bay Leaves",
    ],
    # Baking, Sweeteners & Confectionery
    "Baking, Sweeteners & Additives": [
        "Granulated White Sugar",
        "Brown Sugar / Cane Sugar",
        "Powdered / Confectioners' Sugar",
        "Natural Honey",
        "Maple Syrup / Agave Nectar",
        "Sugar Substitutes (Stevia / Erythritol)",
        "Vanilla Sugar / Vanillin / Vanilla Extract",
        "Baking Powder",
        "Baking Soda",
        "Active Dry / Fresh Yeast",
        "Gelatin",
        "Agar-Agar",
        "Unsweetened Cocoa Powder",
        "Dark / Bittersweet Chocolate",
        "Milk Chocolate",
        "White Chocolate",
        "Chocolate Chips / Drops",
    ],
    # Breads, Wraps & Dough
    "Bread, Dough & Bakery Products": [
        "Thin Lavash / Pita Wraps",
        "Tortillas",
        "Pita Pockets / Flatbreads",
        "Burger Buns",
        "Puff Pastry (Unleavened)",
        "Puff Pastry (Leavened)",
        "Filo / Phyllo Dough",
        "Pizza Dough",
        "Nori Seaweed Sheets",
        "Chicken / Beef / Vegetable Broth",
    ],
    # Non-Alcoholic Beverages & Syrups
    "Non-Alcoholic Drinks": [
        "Still / Mineral Water",
        "Sparkling Water / Club Soda / Tonic Water",
        "Black Tea",
        "Green Tea",
        "Matcha Powder / Tea",
        "Ground Coffee / Whole Beans",
        "Instant Coffee",
        "Apple Juice",
        "Orange Juice",
        "Tomato Juice",
        "Lemonade / Cola",
        "Caramel Syrup",
        "Vanilla Syrup",
        "Fruit / Berry Syrups",
    ],
    # Alcoholic Beverages
    "Alcoholic Beverages": [
        "Dry / Semi-Sweet White Wine",
        "Dry / Semi-Sweet Red Wine",
        "Rosé Wine",
        "Champagne / Sparkling Wine (Prosecco, Asti)",
        "Light / Dark Beer",
        "Apple / Pear Cider",
        "Vodka",
        "Cognac / Brandy",
        "Whiskey / Bourbon",
        "White / Dark Rum",
        "Gin",
        "Tequila",
        "Absinthe",
        "Cream Liqueur (Baileys, etc.)",
        "Coffee Liqueur (Kahlúa, etc.)",
        "Orange Liqueur (Cointreau, Triple Sec)",
        "Herbal Liqueur (Jägermeister, etc.)",
        "Vermouth (Martini, etc.)",
        "Punch / Mulled Wine Bases",
    ],
}


async def seed_recipe_categories(session: AsyncSession) -> None:
    stmt = (
        pg_insert(RecipeCategory)
        .values([{"name": name} for name in RECIPE_CATEGORIES])
        .on_conflict_do_nothing(index_elements=["name"])
    )
    await session.execute(stmt)


async def get_or_create_ingredient_category(session: AsyncSession, name: str) -> object:
    """Insert the category if it doesn't exist yet, then return its id either way.

    ON CONFLICT DO NOTHING only RETURNs a row for the ones it actually inserted — rows
    skipped due to the conflict come back empty, so a category that already existed needs
    a separate SELECT to find its id.
    """
    insert_stmt = (
        pg_insert(IngredientCategory)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(IngredientCategory.id)
    )
    result = await session.execute(insert_stmt)
    category_id = result.scalar_one_or_none()

    if category_id is None:
        existing = await session.execute(
            select(IngredientCategory.id).where(IngredientCategory.name == name)
        )
        category_id = existing.scalar_one()

    return category_id


async def seed_ingredients(session: AsyncSession) -> None:
    for category_name, ingredient_names in INGREDIENT_CATEGORIES.items():
        category_id = await get_or_create_ingredient_category(session, category_name)

        stmt = (
            pg_insert(IngredientCatalog)
            .values(
                [
                    {"name": ingredient_name, "category_id": category_id}
                    for ingredient_name in ingredient_names
                ]
            )
            .on_conflict_do_nothing(index_elements=["name"])
        )
        await session.execute(stmt)


async def main() -> None:
    async with async_session_maker() as session:
        await seed_recipe_categories(session)
        await seed_ingredients(session)
        await session.commit()

    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
