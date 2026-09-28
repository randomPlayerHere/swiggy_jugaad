from pydantic import BaseModel


class Recipe(BaseModel):
    id: str
    name: str
    ingredients: list[str]
    diet: str
    prep_time_minutes: int
    tags: list[str]