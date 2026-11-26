"""GraphQL enums shared by the recipe types and inputs."""

from enum import Enum

import strawberry


@strawberry.enum(description="How difficult a recipe is to make.")
class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@strawberry.enum(description="Unit of measurement for a recipe ingredient's amount.")
class MeasurementUnit(Enum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    PCS = "pcs"
    TBSP = "tbsp"
    TSP = "tsp"
    PINCH = "pinch"
    TO_TASTE = "to_taste"
