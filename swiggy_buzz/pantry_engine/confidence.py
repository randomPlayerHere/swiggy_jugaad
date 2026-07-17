import logging
import math
from datetime import datetime

from swiggy_buzz.config import DEFAULT_DECAY_DAYS
from swiggy_buzz.pantry_engine.constants import *
from swiggy_buzz.store.models import PantryItem

logger = logging.getLogger(__name__)

def usable_life_days(category, household_size) -> float:
