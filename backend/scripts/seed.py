"""Seed the Plateboard database with demo data: 9 zones, 10 cooks, 40 dishes,
5 customers, 1 admin - plus a few months of demo orders and three open carts.

Run from ``backend/``::

    uv run python scripts/seed.py                      # demo passwords per role
    uv run python scripts/seed.py --random-passwords   # random, printed once

What it does:

* ensures the schema is at head (runs the Alembic migrations, like the server
  entry point does),
* creates (or reuses) the fictional accounts below - every email is
  ``first.last@example.com`` and every account of a role gets that role's
  demo password (``DEMO_PASSWORDS``: plateboard-admin / plateboard-cook /
  plateboard-customer), so each panel - /admin, /cook, /account - can be
  opened with known credentials. Existing seeded accounts get their password
  reset to it on every run, so the documented logins always work. With
  ``--random-passwords``, and always when ENVIRONMENT=production, each
  account gets a fresh random password instead (printed once).
* creates dishes missing from the seed list, keyed on ``(cook, name)`` -
  dishes that already exist are left untouched, so edits or deactivations
  made through the dashboard survive a re-run.
* creates the demo zone grid (keyed on slug; existing zones untouched) and
  places each seeded cook in a zone - only if the cook has no zone yet, so a
  zone chosen through ``PATCH /api/cooks/me`` survives a re-run too.
* creates the platform admin (role ``admin`` - the only way that role is ever
  granted; the API cannot), who accepted every seeded kitchen's cook
  application (a day after its cook joined) and verified 8 of the 10.
* files two cook applications from customers (``APPLICATIONS``): one still
  pending - the admin's review queue - and one rejected with a reason; only
  for customers without one.
* gives every new kitchen weekly hours (``KITCHENS`` / ``HOURS_PRESETS``,
  ``DEMO_TIMEZONE``): two take orders any time (so a demo order can always be
  placed), one is paused, the rest keep lunch / dinner / daytime / evening
  hours; a kitchen "opened" when its cook joined.
* gives every seeded shopper (customers and cooks) a "Home" address - two
  customers also a "Work" one - in a grid zone, only if they have none.
* gives the dashboards something to draw: newly created accounts get a
  deterministic "joined" date in the past, and - only while the seeded
  accounts have no orders at all - 200 demo orders spread over the last four
  months (fixed random seed; mostly completed, some cancelled - cooks say
  why they turned one down), 4 completed earlier today and 12 recent ones
  still open (placed / accepted / ready), and an open cart for three
  customers (only if they have none). Re-runs never add a second history.
* saves a few favourite dishes for two customers (``DEMO_FAVOURITES``) -
  only for customers without any, so a list edited in the UI survives a
  re-run. One of the showcase customer's favourites is a dish its cook has
  since hidden, so the list shows an unavailable dish.
* writes demo reviews of received dishes + some cook replies, and their
  recent notifications (see ``_ensure_demo_reviews``).
* makes one kitchen the showcase (``SHOWCASE_COOK``, Aiko Tanaka): about a
  third of the history, today's orders and a queue of open requests, so the
  cook dashboard is full when you log in as her.
* fills the notification inboxes - only while the seeded accounts have no
  order notifications yet: every step of the last
  :data:`NOTIFICATION_DAYS` days of orders, written by the same code as live
  orders (``app.modules.orders.notifications``, backdated to each step), the
  kitchens' verification notices and the applications' notices. Anything
  older than :data:`UNREAD_HOURS` is marked read; answered requests are read
  too.

All names are invented; any resemblance to real persons is coincidental.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import random
import secrets
import sys
import unicodedata
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Import `app.*` whether this runs as `python scripts/seed.py` (sys.path[0]
# would otherwise be scripts/) or as `python -m scripts.seed`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.core.db import session_scope
from app.main import run_migrations
from app.modules.addresses.models import Address
from app.modules.addresses.service import delivery_snapshot
from app.modules.auth.models import (
    ROLE_ADMIN,
    ROLE_COOK,
    ROLE_CUSTOMER,
    CookApplicationStatus,
    CookProfile,
    User,
)
from app.modules.auth.security import hash_password
from app.modules.cart.models import Cart, CartItem
from app.modules.dishes.models import ALLERGEN_VALUES, Dish
from app.modules.favourites.models import FavouriteDish
from app.modules.notifications import service as notifications
from app.modules.notifications.catalog import (
    CookApplicationPayload,
    NoPayload,
    NotificationType,
)
from app.modules.notifications.models import Audience, Notification
from app.modules.orders import notifications as order_notifications
from app.modules.orders.models import CancelledBy, Order, OrderItem, OrderStatus, Party
from app.modules.reviews import notifications as review_notifications
from app.modules.reviews.models import Review
from app.modules.reviews.service import full_cycle_conditions
from app.modules.zones.models import Zone
from app.modules.zones.schemas import ZoneCreate
from app.shared.base import utcnow


@dataclasses.dataclass(frozen=True)
class DishSpec:
    name: str
    description: str
    price: int  # minor units
    portions: int
    ingredients: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()  # tokens from app.modules.dishes.models.Allergen
    dietary_tags: tuple[str, ...] = ()
    active: bool = True


@dataclasses.dataclass(frozen=True)
class CookSpec:
    name: str
    headline: str
    area: str
    bio: str
    specialties: tuple[str, ...]
    zone: str  # slug from ZONES: where the kitchen sits on the service grid
    dishes: tuple[DishSpec, ...]


# The demo service grid: (slug, name, x, y), x = column, y = row. Distances
# between zones are Manhattan grid steps (app.modules.zones.grid).
#
#        x=0          x=1            x=2
#  y=0   north-gate   old-town       hillside
#  y=1   riverside    market-square  university
#  y=2   harbour      station        garden-district
ZONES: tuple[tuple[str, str, int, int], ...] = (
    ("north-gate", "North Gate", 0, 0),
    ("old-town", "Old Town", 1, 0),
    ("hillside", "Hillside", 2, 0),
    ("riverside", "Riverside", 0, 1),
    ("market-square", "Market Square", 1, 1),
    ("university", "University", 2, 1),
    ("harbour", "Harbour", 0, 2),
    ("station", "Station", 1, 2),
    ("garden-district", "Garden District", 2, 2),
)


# 10 cooks x 4 dishes = 40 dishes; two are deactivated on purpose so the
# dashboard has something to reactivate and the public menu something to hide.
COOKS: tuple[CookSpec, ...] = (
    CookSpec(
        name="Nadia Rahman",
        headline="Biryani, reinvented one pot at a time",
        area="Dhanmondi, Dhaka",
        bio="Third-generation home cook chasing the perfect crunchy alu.",
        specialties=("biryani", "korma"),
        zone="market-square",
        dishes=(
            DishSpec(
                "Hyderabadi Chicken Biryani",
                "Dum-cooked basmati with saffron and yoghurt-marinated chicken.",
                890, 12,
                ("basmati rice", "chicken", "yoghurt", "saffron", "fried onions"),
                ("milk",), ("halal",),
            ),
            DishSpec(
                "Mutton Tehari",
                "Spicy short-grain rice with slow-cooked mutton.",
                1050, 10,
                ("mutton", "rice", "mustard oil", "curry leaves"),
                ("mustard",), ("halal", "spicy"),
            ),
            DishSpec(
                "Morog Polao",
                "Home-style chicken pilaf with a boiled egg on top.",
                800, 8,
                ("chicken", "rice", "eggs", "cinnamon", "cardamom"),
                ("eggs",), ("halal",),
            ),
            DishSpec(
                "Begum's Chicken Korma",
                "Mild, creamy korma thickened with ground cashews.",
                950, 10,
                ("chicken", "cashews", "yoghurt", "cream", "cardamom"),
                ("milk", "nuts"), ("halal", "mild"),
            ),
        ),
    ),
    CookSpec(
        name="Marco Greco",
        headline="Nonna's recipes, wood-fired oven",
        area="Quartieri Spagnoli, Napoli",
        bio="Pasta is a trade, ragù is patience.",
        specialties=("pasta", "pizza"),
        zone="old-town",
        dishes=(
            DishSpec(
                "Tagliatelle al Ragù",
                "Eight-hour beef-and-pork ragù over hand-cut pasta.",
                1350, 8,
                ("beef", "pork", "tomato", "onion", "flour", "eggs"),
                ("gluten", "eggs"), (),
            ),
            DishSpec(
                "Pizza Margherita",
                "Wood-fired dough, San Marzano tomatoes, fior di latte.",
                900, 6,
                ("flour", "tomatoes", "mozzarella", "basil", "olive oil"),
                ("gluten", "milk"), ("vegetarian",),
            ),
            DishSpec(
                "Risotto alla Milanese",
                "Carnaroli rice with saffron, marrow and parmesan.",
                1250, 6,
                ("rice", "saffron", "beef marrow", "parmesan", "butter", "white wine"),
                ("milk", "sulphites"), (),
            ),
            DishSpec(
                "Lasagna della Nonna",
                "Layers of fresh pasta, ragù and béchamel.",
                1100, 8,
                ("flour", "eggs", "beef", "tomato", "parmesan", "butter"),
                ("gluten", "eggs", "milk"), (),
            ),
        ),
    ),
    CookSpec(
        name="Aiko Tanaka",
        headline="Comfort food from an Osaka kitchen",
        area="Namba, Osaka",
        bio="Ramen first, questions later.",
        specialties=("ramen", "okonomiyaki"),
        zone="station",
        dishes=(
            DishSpec(
                "Tonkotsu Ramen",
                "Eighteen-hour pork broth with chashu and ajitama egg.",
                1200, 6,
                ("pork", "ramen noodles", "soft egg", "green onion", "sesame"),
                ("gluten", "eggs", "sesame"), (),
            ),
            DishSpec(
                "Okonomiyaki",
                "Osaka cabbage pancake with bonito, sauce and mayo.",
                950, 4,
                ("cabbage", "flour", "eggs", "pork", "bonito flakes", "mayo"),
                ("gluten", "eggs", "fish", "molluscs", "soy"), (),
            ),
            DishSpec(
                "Chicken Katsu Curry",
                "Panko-crusted cutlet under mild Japanese curry.",
                1050, 6,
                ("chicken", "panko", "potatoes", "carrots", "curry roux"),
                ("gluten", "soy"), ("mild",),
            ),
            DishSpec(
                "Oden no Mono",
                "Winter simmer: daikon, egg and konnyaku in dashi.",
                900, 4,
                ("daikon", "eggs", "konnyaku", "dashi"),
                ("eggs", "fish", "soy"), ("winter special",),
                active=False,
            ),
        ),
    ),
    CookSpec(
        name="Priya Sharma",
        headline="Home-style vegetarian, cooked to order",
        area="Civil Lines, Jaipur",
        bio="Marwadi kitchen, no shortcuts, no eggs.",
        specialties=("vegetarian", "thali"),
        zone="market-square",
        dishes=(
            DishSpec(
                "Paneer Tikka Masala",
                "Charred paneer swimming in creamy tomato gravy.",
                750, 8,
                ("paneer", "tomatoes", "cream", "bell pepper", "garam masala"),
                ("milk",), ("vegetarian", "spicy"),
            ),
            DishSpec(
                "Chana Masala",
                "Slow-cooked chickpeas sharpened with amchur.",
                550, 10,
                ("chickpeas", "onion", "tomato", "ginger", "amchur"),
                (), ("vegan", "gluten free"),
            ),
            DishSpec(
                "Baingan Bharta",
                "Smoky roasted aubergine mashed with tomatoes.",
                600, 8,
                ("aubergine", "tomato", "coriander", "mustard oil"),
                ("mustard",), ("vegetarian", "gluten free"),
            ),
            DishSpec(
                "Aloo Gobi",
                "Dry cauliflower-and-potato with turmeric.",
                500, 8,
                ("cauliflower", "potato", "turmeric", "cumin"),
                (), ("vegan", "gluten free"),
            ),
        ),
    ),
    CookSpec(
        name="Tomáš Novák",
        headline="Svíčková on Sunday, every Sunday",
        area="Smíchov, Praha",
        bio="Czech home cooking and honest dumplings.",
        specialties=("czech", "soups"),
        zone="hillside",
        dishes=(
            DishSpec(
                "Svíčková na smetaně",
                "Marinated beef in a cream-vegetable sauce, with dumplings.",
                1400, 6,
                ("beef", "root vegetables", "cream", "bread dumplings", "lingonberries"),
                ("gluten", "milk", "celery"), (),
            ),
            DishSpec(
                "Bramborová Polévka",
                "Velvety potato soup with smoked ham and marjoram.",
                450, 10,
                ("potatoes", "smoked ham", "marjoram", "carrot"),
                ("sulphites",), (),
            ),
            DishSpec(
                "Kulajda",
                "Sour mushroom-and-dill soup with a soft egg.",
                650, 6,
                ("mushrooms", "dill", "cream", "egg", "potatoes"),
                ("milk", "eggs"), ("vegetarian",),
            ),
            DishSpec(
                "Svestkové Knedlaky",
                "Plum dumplings under cinnamon sugar.",
                500, 8,
                ("flour", "plums", "butter", "cinnamon", "eggs"),
                ("gluten", "milk", "eggs"), ("vegetarian", "sweet"),
            ),
        ),
    ),
    CookSpec(
        name="Fatima El-Sayed",
        headline="Lebanese grill and mezze master",
        area="Hamra, Beirut",
        bio="If the parsley isn't hand-chopped, it isn't tabbouleh.",
        specialties=("mezze", "grill"),
        zone="riverside",
        dishes=(
            DishSpec(
                "Chicken Shawarma Platter",
                "Garlic-toum chicken, pickles and fresh flatbread.",
                850, 6,
                ("chicken", "flatbread", "garlic sauce", "pickles", "tahini"),
                ("gluten", "sesame", "milk"), ("halal",),
            ),
            DishSpec(
                "Tabbouleh",
                "Hand-chopped parsley and bulgur with lemon.",
                550, 8,
                ("parsley", "bulgur", "tomato", "mint", "lemon"),
                ("gluten",), ("vegan",),
            ),
            DishSpec(
                "Hummus bi-Tahina",
                "Stone-ground chickpeas with sesame paste.",
                450, 10,
                ("chickpeas", "tahini", "lemon", "garlic"),
                ("sesame",), ("vegan", "gluten free"),
            ),
            DishSpec(
                "Grilled Halloumi",
                "Halloumi with olives, oregano and good olive oil.",
                700, 4,
                ("halloumi", "olives", "oregano", "olive oil"),
                ("milk",), ("vegetarian", "gluten free"),
            ),
        ),
    ),
    CookSpec(
        name="Kwame Mensah",
        headline="West African classics, big pots only",
        area="Osu, Accra",
        bio="Jollof judge in retirement; still cooking weekends.",
        specialties=("jollof", "soups"),
        zone="harbour",
        dishes=(
            DishSpec(
                "Jollof Rice",
                "Smoky one-pot rice over a long-reduced tomato base.",
                750, 12,
                ("long grain rice", "tomatoes", "scotch bonnet", "ginger", "thyme"),
                (), ("gluten free",),
            ),
            DishSpec(
                "Groundnut Soup",
                "Rich peanut soup with chicken and red rice.",
                950, 8,
                ("peanuts", "chicken", "palm oil", "pepper", "onion"),
                ("peanuts",), ("gluten free",),
            ),
            DishSpec(
                "Waakye",
                "Rice-and-beans with shito, gari and a boiled egg.",
                650, 10,
                ("rice", "beans", "shito", "gari", "eggs"),
                ("eggs",), (),
            ),
            DishSpec(
                "Kelewele",
                "Spiced fried plantain cubes with roasted peanuts.",
                400, 6,
                ("plantain", "ginger", "cayenne", "peanuts"),
                ("peanuts",), ("vegan", "gluten free"),
            ),
        ),
    ),
    CookSpec(
        name="Olena Kovalenko",
        headline="Pierogi and borscht like grandma's",
        area="Podil, Kyiv",
        bio="Dill is a food group. Sour cream is a seasoning.",
        specialties=("dumplings", "soups"),
        zone="north-gate",
        dishes=(
            DishSpec(
                "Borscht",
                "Beet soup with cabbage, dill and a cold dollop.",
                550, 10,
                ("beets", "cabbage", "potato", "sour cream", "dill"),
                ("milk", "celery"), ("vegetarian",),
            ),
            DishSpec(
                "Pierogi Ruskie",
                "Potato-and-cheese dumplings with fried onion.",
                700, 20,
                ("flour", "potato", "farmer cheese", "onion", "butter"),
                ("gluten", "milk"), ("vegetarian",),
            ),
            DishSpec(
                "Golubtsi",
                "Cabbage rolls stuffed with millet and mushrooms.",
                800, 8,
                ("cabbage", "millet", "mushrooms", "tomato", "carrot"),
                (), ("vegan",),
            ),
            DishSpec(
                "Syrnyky",
                "Quark pancakes with berry compote (weekends only).",
                600, 6,
                ("quark", "eggs", "flour", "berries", "sugar"),
                ("gluten", "eggs", "milk"), ("vegetarian", "sweet"),
                active=False,
            ),
        ),
    ),
    CookSpec(
        name="Diego Fuentes",
        headline="Abuela's mole, done right",
        area="Teotitlán, Oaxaca",
        bio="Thirty ingredients in the mole, zero shortcuts.",
        specialties=("mexican", "moles"),
        zone="university",
        dishes=(
            DishSpec(
                "Mole Negro con Pollo",
                "Black mole with poached chicken and sesame seeds.",
                1350, 8,
                ("chicken", "chilhuacle chiles", "chocolate", "plantain", "sesame"),
                ("sesame", "nuts"), (),
            ),
            DishSpec(
                "Arroz con Frijoles",
                "Cilantro-lime rice with black beans.",
                550, 12,
                ("rice", "black beans", "cilantro", "lime", "onion"),
                (), ("vegan", "gluten free"),
            ),
            DishSpec(
                "Sopa de Tortilla",
                "Tomato broth, crispy corn tortillas, avocado, queso.",
                650, 6,
                ("tomatillo", "corn tortillas", "avocado", "queso fresco", "chile"),
                ("milk",), ("vegetarian",),
            ),
            DishSpec(
                "Chiles en Nogada",
                "Poblano peppers stuffed and dressed in walnut cream.",
                1100, 6,
                ("poblano", "walnuts", "goat cheese", "peach", "pear"),
                ("nuts", "milk"), ("seasonal",),
            ),
        ),
    ),
    CookSpec(
        name="Mei-Ling Chen",
        headline="Dim sum every Sunday, steamed to order",
        area="Liwan, Guangzhou",
        bio="If the har gow has fewer than ten pleats, send it back.",
        specialties=("dim sum", "cantonese"),
        zone="garden-district",
        dishes=(
            DishSpec(
                "Har Gow",
                "Crystal shrimp dumplings - ten pieces per basket.",
                850, 10,
                ("shrimp", "bamboo shoots", "wheat starch", "sesame oil"),
                ("crustaceans", "gluten", "sesame"), (),
            ),
            DishSpec(
                "Char Siu Bao",
                "Steamed buns with honey-glazed barbecue pork.",
                750, 8,
                ("flour", "pork", "hoisin", "honey", "egg"),
                ("gluten", "soy", "eggs"), (),
            ),
            DishSpec(
                "Custard Egg Tart",
                "Flaky pastry under silky milk custard.",
                550, 6,
                ("flour", "eggs", "milk", "sugar", "butter"),
                ("gluten", "eggs", "milk"), ("sweet",),
            ),
            DishSpec(
                "Mapo Tofu",
                "Silken tofu in fiery chilli-bean paste.",
                700, 8,
                ("tofu", "doubanjiang", "ground pork", "sichuan pepper", "scallion"),
                ("soy",), ("spicy",),
            ),
        ),
    ),
)

CUSTOMERS: tuple[str, ...] = (
    "Sam Porter",
    "Grace Okoro",
    "Yusuf Demir",
    "Hana Kobayashi",
    "Leo Fischer",
)


#: The platform operator(s): role ``admin`` only (they do not shop or cook).
ADMINS: tuple[str, ...] = ("Morgan Ellis",)

# --- demo logins -----------------------------------------------------------------
#: One known password per role, so every panel can be opened without reading
#: the seed output (documented in the README). Every seeded account of that
#: role uses it, and a re-run resets it. Never used in production: with
#: ENVIRONMENT=production (or --random-passwords) each account gets a fresh
#: random password instead, printed once.
DEMO_PASSWORDS: dict[str, str] = {
    "admin": "plateboard-admin",
    "cook": "plateboard-cook",
    "customer": "plateboard-customer",
}
# --- kitchens: verification + hours ----------------------------------------------
#: The demo kitchens' time zone (cooks change theirs on /cook/hours; the UI
#: shows times in the viewer's own zone).
DEMO_TIMEZONE = "UTC"


def _every(days: range | tuple[int, ...], *spans: tuple[str, str]) -> list[dict[str, object]]:
    """Weekly windows: ``spans`` on each of ``days`` (0 = Monday)."""
    return [{"day": day, "opens": opens, "closes": closes} for day in days for opens, closes in spans]


#: Named weekly schedules (kitchen time).
HOURS_PRESETS: dict[str, list[dict[str, object]]] = {
    "long-days": _every(range(7), ("08:00", "23:00")),
    "lunch-and-dinner": _every(range(1, 7), ("11:30", "14:30"), ("17:30", "21:30")),
    "daytime": _every(range(6), ("09:00", "17:00")),
    "evenings": _every(range(5), ("16:00", "22:00")) + _every((5, 6), ("12:00", "22:00")),
    "anytime": [],  # no fixed hours: orders any time (always orderable in the demo)
}
#: Per seeded kitchen: (hours preset, verified by the admin, orders paused).
#: A mix, so every badge and availability state shows somewhere.
KITCHENS: dict[str, tuple[str, bool, bool]] = {
    "Nadia Rahman": ("anytime", True, False),
    "Marco Greco": ("evenings", False, False),
    "Aiko Tanaka": ("long-days", True, False),  # the showcase kitchen
    "Priya Sharma": ("lunch-and-dinner", True, False),
    "Tomáš Novák": ("daytime", True, False),
    "Fatima El-Sayed": ("lunch-and-dinner", True, False),
    "Kwame Mensah": ("anytime", True, False),
    "Olena Kovalenko": ("daytime", True, True),  # paused: "on a short break"
    "Diego Fuentes": ("evenings", True, False),
    "Mei-Ling Chen": ("lunch-and-dinner", False, False),
}
#: Every seeded kitchen's application was accepted this long after its cook
#: joined (and submitted when they joined).
REVIEWED_AFTER = timedelta(days=1)
#: A verified kitchen was checked this long after the cook joined.
VERIFIED_AFTER = timedelta(days=3)


@dataclasses.dataclass(frozen=True)
class ApplicationSpec:
    """A customer's cook application (``CUSTOMERS`` name)."""

    name: str
    headline: str
    specialties: tuple[str, ...]
    zone: str
    status: CookApplicationStatus
    submitted_days_ago: int
    reason: str | None = None  # a rejection's explanation


#: Demo cook applications: one waiting in the admin's review queue, one
#: rejected (the applicant may apply again). Never the showcase customer.
APPLICATIONS: tuple[ApplicationSpec, ...] = (
    ApplicationSpec(
        name="Grace Okoro",
        headline="West African stews, jollof and puff-puff",
        specialties=("jollof", "egusi", "west african"),
        zone="riverside",
        status=CookApplicationStatus.PENDING,
        submitted_days_ago=1,
    ),
    ApplicationSpec(
        name="Leo Fischer",
        headline="Weekend sourdough and pretzels",
        specialties=("baking", "sourdough"),
        zone="old-town",
        status=CookApplicationStatus.REJECTED,
        submitted_days_ago=9,
        reason="Please add where and how you bake (your kitchen set-up) and "
        "apply again.",
    ),
)

#: Where each role's panel lives in the frontend.
PANELS: dict[str, str] = {"admin": "/admin", "cook": "/cook", "customer": "/account"}
#: The customer with the fullest demo account (orders, an open order, a bag):
#: log in as them to see the customer dashboard at /account.
SHOWCASE_CUSTOMER = "Sam Porter"

# --- demo history (dashboards) ---------------------------------------------------
#: Fixed seed: the same demo history on every fresh database.
HISTORY_RANDOM_SEED = 20261108
#: Demo orders created on a database whose seeded accounts have none: a
#: history of settled ones (completed/cancelled) plus a few recent, still
#: open ones (placed/accepted/ready) so the cook's "to do" list is not empty.
DEMO_ORDERS = 200
DEMO_OPEN_ORDERS = 12
#: Orders completed earlier *today* (UTC) in the showcase kitchen, so the cook
#: dashboard's "today" earnings are not zero right after seeding.
DEMO_TODAY_ORDERS = 4
#: The kitchen with the fullest demo history - log in as this cook to see the
#: cook dashboard with every chart and list populated. It also keeps one
#: private dish (see its specs), for the public/private switch.
SHOWCASE_COOK = "Aiko Tanaka"
#: Share of the settled history placed with the showcase kitchen on purpose
#: (it also gets its fair share of the rest).
SHOWCASE_SHARE = 0.3
#: Statuses of the showcase kitchen's open orders: requests to accept or
#: reject, one cooking, one ready for handover (the rest of the open orders
#: go to random kitchens).
SHOWCASE_OPEN_STATUSES: tuple[OrderStatus, ...] = (
    OrderStatus.PLACED,
    OrderStatus.PLACED,
    OrderStatus.ACCEPTED,
    OrderStatus.READY,
    OrderStatus.PLACED,
    OrderStatus.ACCEPTED,
)
#: The showcase kitchen's open orders were placed this many minutes ago (at most).
SHOWCASE_OPEN_MINUTES = 180
#: What a cook tells the customer when turning an order down (before / after
#: accepting it) - ``Order.cancel_reason``.
REJECT_REASONS: tuple[str, ...] = (
    "Sold out for today - sorry!",
    "Kitchen closed this evening",
    "Too many orders right now",
    "Can't get it ready in time today",
)
CANCEL_REASONS: tuple[str, ...] = (
    "Ran out of a key ingredient",
    "Family emergency - so sorry",
)
#: The open ones were placed within this many hours before the run.
OPEN_ORDER_HOURS = 36
#: Oldest demo order, in days before the run.
HISTORY_DAYS = 120
#: Orders placed within this many days get their notifications seeded.
NOTIFICATION_DAYS = 7
#: Seeded notifications younger than this stay unread (older ones are read).
UNREAD_HOURS = 24
#: How long ago newly created accounts "joined": (oldest, newest) days back.
#: Cooks joined before customers; a few customers are recent, so the admin's
#: signup chart has points inside its default 30-day window.
JOINED_DAYS_AGO: dict[str, tuple[int, int]] = {
    "admin": (200, 200),
    "cook": (150, 190),
    "customer": (3, 140),
}
#: Invented streets of the one demo city the zone grid maps.
DEMO_CITY = "Riverton"
STREETS: tuple[str, ...] = (
    "Lantern Lane",
    "Copper Street",
    "Willow Row",
    "Harbour Walk",
    "Mill Road",
    "Orchard Way",
    "Bellfounders Yard",
    "Quarry Hill",
    "Tanner's Close",
)
#: Customers (by index in CUSTOMERS) with a second, "Work" address.
WORK_ADDRESSES: tuple[int, ...] = (0, 1)
#: Customers (by index in CUSTOMERS) who get an open cart: (cook index, lines).
#: Cook 2 is the showcase kitchen - its dashboard shows the cart demand.
DEMO_CARTS: tuple[tuple[int, int, int], ...] = ((0, 0, 2), (1, 3, 1), (2, 2, 2))
#: Favourite dishes per customer, newest first, as ``(cook, dish)`` names.
#: The showcase customer's list mixes kitchens (their bag holds Nadia's
#: dishes, so adding Kwame's Jollof asks to start a new bag) and includes
#: Aiko's private "Oden no Mono": saved while it was public, hidden since -
#: an unavailable favourite. Only for customers without any favourites.
DEMO_FAVOURITES: dict[str, tuple[tuple[str, str], ...]] = {
    SHOWCASE_CUSTOMER: (
        ("Kwame Mensah", "Jollof Rice"),
        ("Aiko Tanaka", "Oden no Mono"),
        ("Nadia Rahman", "Hyderabadi Chicken Biryani"),
        ("Mei-Ling Chen", "Custard Egg Tart"),
        ("Marco Greco", "Pizza Margherita"),
    ),
    "Grace Okoro": (
        ("Fatima El-Sayed", "Tabbouleh"),
        ("Priya Sharma", "Chana Masala"),
        ("Olena Kovalenko", "Borscht"),
    ),
}
#: Days between two demo favourites being saved (the newest a day ago).
FAVOURITE_SPACING_DAYS = 3

# --- demo reviews ------------------------------------------------------------------
REVIEW_RANDOM_SEED = 20261109
REVIEW_SHARE = 0.6
RATING_WEIGHTS: tuple[tuple[int, int], ...] = ((5, 48), (4, 30), (3, 12), (2, 6), (1, 4))
REVIEW_COMMENTS: dict[int, tuple[str | None, ...]] = {
    5: (
        "Absolutely delicious - it tastes like home.",
        "Generous portion and beautifully packed.",
        "Best I've had in the neighbourhood!",
        None,
    ),
    4: ("Really good, would order again.", "Tasty - a little more spice next time?", None),
    3: ("Good flavour, but a small portion.", "Decent - it was lukewarm by the time I got home."),
    2: ("Too salty for me this time.",),
    1: ("Not what I expected, sadly.",),
}
REPLIES_HAPPY: tuple[str, ...] = (
    "Thank you so much - see you next time!",
    "So glad you enjoyed it!",
)
REPLIES_SORRY: tuple[str, ...] = (
    "Thanks for the honest feedback - I'll adjust it.",
    "Sorry it wasn't up to scratch - next one is on me.",
)
REPLY_SHARE = 0.4
SHOWCASE_REPLY_SHARE = 0.75
# The showcase customer's newest received dishes stay unreviewed, so the
# "to rate" list is never empty after seeding.
SHOWCASE_UNREVIEWED = 2


@dataclasses.dataclass
class SeedAccount:
    email: str
    password: str
    display_name: str
    kind: str  # "admin" | "cook" | "customer"


@dataclasses.dataclass
class SeedResult:
    accounts: list[SeedAccount] = dataclasses.field(default_factory=list)
    random_passwords: bool = False
    zones_created: int = 0
    zones_existing: int = 0
    users_created: int = 0
    users_existing: int = 0
    dishes_created: int = 0
    dishes_existing: int = 0
    orders_created: int = 0
    orders_existing: int = 0
    carts_created: int = 0
    favourites_created: int = 0
    reviews_created: int = 0
    replies_created: int = 0
    addresses_created: int = 0
    applications_created: int = 0
    notifications_created: int = 0


def email_for(full_name: str) -> str:
    """`Nadia Rahman` -> `nadia.rahman@example.com` (lowercase, invented).

    Diacritics are folded to ASCII (``Tomáš`` -> ``tomas``): the email must
    survive the login schema's EmailStr validation, which is not Unicode-local
    part friendly. Re-running must produce the same address, so keep this
    function deterministic.
    """
    slug = ".".join(part.lower() for part in full_name.split())
    slug = unicodedata.normalize("NFKD", slug).encode("ascii", "ignore").decode()
    return f"{slug}@example.com"


def generate_password() -> str:
    """Fresh random credential (>= 8 chars per auth rules) - used instead of
    the demo passwords with ``--random-passwords`` and always in production."""
    return secrets.token_urlsafe(9)


def password_for(kind: str, *, random_passwords: bool) -> str:
    """The documented demo password of the role, or a random one."""
    return generate_password() if random_passwords else DEMO_PASSWORDS[kind]


async def _ensure_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    password: str,
    roles: list[str],
    bio: str | None = None,
    area: str | None = None,
    joined: datetime | None = None,
) -> tuple[User, bool]:
    """Create the account, or reuse it with a reset password.

    Returns ``(user, created)``. Password reset is deliberate: the run prints
    new credentials, so the printed ones must always work. ``joined`` backdates
    a *new* account (an existing one keeps its real creation time).
    """
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        existing.display_name = display_name
        existing.bio = bio if bio is not None else existing.bio
        existing.area = area if area is not None else existing.area
        # Roles grow, never replace (mirrors accepting a cook application).
        existing.roles = list(dict.fromkeys([*(existing.roles or []), *roles]))
        existing.password_hash = hash_password(password)
        return existing, False
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        bio=bio,
        area=area,
        roles=list(roles),
        created_at=joined,
        updated_at=joined,
    )
    session.add(user)
    # The UUID primary key is filled in at INSERT time; the cook profile and
    # dish rows below use it as an FK, so flush now rather than at commit.
    await session.flush()
    return user, True


async def _ensure_zones(session: AsyncSession, result: SeedResult) -> dict[str, Zone]:
    """Create missing demo zones (keyed on slug); return every zone by slug."""
    existing = {zone.slug: zone for zone in (await session.scalars(select(Zone))).all()}
    for slug, name, x, y in ZONES:
        if slug in existing:
            result.zones_existing += 1
            continue
        spec = ZoneCreate(slug=slug, name=name, x=x, y=y)  # same rules as the API
        zone = Zone(**spec.model_dump())
        session.add(zone)
        existing[slug] = zone
        result.zones_created += 1
    await session.flush()  # ids are needed for the cook placements below
    return existing


async def _ensure_cook_profile(
    session: AsyncSession,
    user: User,
    spec: CookSpec,
    zones: dict[str, Zone],
    admin: User | None,
) -> None:
    """Create the kitchen (opened when the cook joined; hours, pause and
    verification from :data:`KITCHENS`). An existing kitchen keeps whatever
    was set through the UI - hours, pause, verification - and only gets a zone
    if it has none."""
    zone = zones[spec.zone]
    profile = await session.get(CookProfile, user.id)
    if profile is not None:
        # Leave dashboard edits alone; only place cooks that have no zone yet
        # (e.g. a database seeded before zones existed).
        if profile.zone_id is None:
            profile.zone = zone
        return
    preset, verified, paused = KITCHENS[spec.name]
    session.add(
        CookProfile(
            user_id=user.id,
            headline=spec.headline,
            specialties=list(spec.specialties),
            zone=zone,
            timezone=DEMO_TIMEZONE,
            opening_hours=[dict(window) for window in HOURS_PRESETS[preset]],
            orders_paused=paused,
            verified_at=user.created_at + VERIFIED_AFTER if verified and admin else None,
            verified_by_id=admin.id if verified and admin else None,
            # Applied when the cook joined, accepted a day later.
            status=CookApplicationStatus.ACCEPTED.value,
            submitted_at=user.created_at,
            reviewed_at=user.created_at + REVIEWED_AFTER,
            reviewed_by_id=admin.id if admin else None,
            # "Cooking since" = when the cook joined, not when the seed ran.
            created_at=user.created_at,
            updated_at=user.created_at,
        )
    )


async def _ensure_applications(
    session: AsyncSession,
    customers: list[User],
    zones: dict[str, Zone],
    admin: User | None,
    now: datetime,
    result: SeedResult,
) -> None:
    """File :data:`APPLICATIONS` for customers who have no cook profile yet
    (so a real application or a decision made in the UI is never touched)."""
    by_name = {user.display_name: user for user in customers}
    for spec in APPLICATIONS:
        user = by_name[spec.name]
        if await session.get(CookProfile, user.id) is not None:
            continue
        submitted = max(user.created_at, now - timedelta(days=spec.submitted_days_ago))
        decided = spec.status is not CookApplicationStatus.PENDING
        session.add(
            CookProfile(
                user_id=user.id,
                headline=spec.headline,
                specialties=list(spec.specialties),
                zone=zones[spec.zone],
                timezone=DEMO_TIMEZONE,
                status=spec.status.value,
                submitted_at=submitted,
                reviewed_at=submitted + REVIEWED_AFTER if decided else None,
                reviewed_by_id=admin.id if decided and admin else None,
                rejection_reason=spec.reason,
                created_at=submitted,
                updated_at=submitted,
            )
        )
        result.applications_created += 1
    await session.flush()


async def _ensure_dish(
    session: AsyncSession, cook_id: uuid.UUID, spec: DishSpec
) -> bool:
    """Create the dish if missing; never overwrite an existing one.

    Returns True when a row was added. Idempotency key is (cook, name).
    """
    unknown = [a for a in spec.allergens if a not in ALLERGEN_VALUES]
    if unknown:
        raise ValueError(f"seed dish {spec.name!r}: unknown allergens {unknown}")
    existing = await session.scalar(
        select(Dish).where(Dish.cook_id == cook_id, Dish.name == spec.name)
    )
    if existing is not None:
        return False
    session.add(
        Dish(
            cook_id=cook_id,
            name=spec.name,
            description=spec.description,
            price=spec.price,
            portions=spec.portions,
            ingredients=list(spec.ingredients),
            allergens=list(spec.allergens),
            dietary_tags=list(spec.dietary_tags),
            active=spec.active,
        )
    )
    return True


def joined_at(email: str, kind: str, now: datetime) -> datetime:
    """Deterministic past "joined" time for a new account (hash of the email,
    so every fresh database gets the same spread)."""
    oldest, newest = JOINED_DAYS_AGO[kind]
    digest = int(hashlib.sha256(email.encode()).hexdigest(), 16)
    days = newest + digest % (oldest - newest + 1)
    minutes = digest // 1000 % 1440
    return now - timedelta(days=days, minutes=minutes)


def _street(user: User, salt: str) -> tuple[str, str]:
    """Deterministic invented street line + phone for a seeded account."""
    digest = int(hashlib.sha256(f"{user.email}:{salt}".encode()).hexdigest(), 16)
    line1 = f"{digest % 180 + 1} {STREETS[digest // 7 % len(STREETS)]}"
    phone = f"+1 555 01{digest // 11 % 100:02d}"
    return line1, phone


async def _ensure_addresses(
    session: AsyncSession,
    customers: list[User],
    cooks: list[User],
    zones: dict[str, Zone],
    result: SeedResult,
) -> dict[uuid.UUID, Address]:
    """A default "Home" address per seeded shopper (cooks: in their kitchen's
    zone; customers: spread over the grid) - only for accounts without any.
    Returns every seeded shopper's default address (for the demo orders)."""
    slugs = [slug for slug, _name, _x, _y in ZONES]
    homes: dict[uuid.UUID, str] = {
        user.id: spec.zone for user, spec in zip(cooks, COOKS, strict=True)
    }
    for index, user in enumerate(customers):
        homes[user.id] = slugs[(index * 4) % len(slugs)]
    defaults: dict[uuid.UUID, Address] = {}
    fresh: set[uuid.UUID] = set()  # accounts whose address book starts now
    for user in [*customers, *cooks]:
        existing = list(
            (
                await session.scalars(select(Address).where(Address.user_id == user.id))
            ).all()
        )
        if existing:
            defaults[user.id] = next((a for a in existing if a.is_default), existing[0])
            continue
        line1, phone = _street(user, "home")
        home = Address(
            user_id=user.id,
            label="Home",
            recipient=user.display_name or user.email,
            phone=phone,
            line1=line1,
            city=DEMO_CITY,
            zone=zones[homes[user.id]],
            is_default=True,
        )
        session.add(home)
        defaults[user.id] = home
        fresh.add(user.id)
        result.addresses_created += 1
    for index in WORK_ADDRESSES:
        user = customers[index]
        if user.id in fresh:  # never add to a book the account already had
            line1, phone = _street(user, "work")
            session.add(
                Address(
                    user_id=user.id,
                    label="Work",
                    recipient=user.display_name or user.email,
                    phone=phone,
                    line1=line1,
                    line2="Reception",
                    city=DEMO_CITY,
                    instructions="Leave it with the front desk",
                    zone=zones["market-square"],
                    is_default=False,
                )
            )
            result.addresses_created += 1
    await session.flush()
    return defaults


async def _active_dishes(session: AsyncSession, cook_id: uuid.UUID) -> list[Dish]:
    stmt = (
        select(Dish)
        .where(Dish.cook_id == cook_id, Dish.active.is_(True))
        .order_by(Dish.name)
    )
    return list((await session.scalars(stmt)).all())


def _demo_status(
    rng: random.Random,
    placed: datetime,
    now: datetime,
    *,
    settled: bool,
    target: OrderStatus | None = None,
) -> tuple[OrderStatus, dict[str, datetime | str]]:
    """A plausible status - settled (completed/cancelled) or open (placed /
    accepted / ready), or the given ``target`` - with the timestamp of every
    step the order went through, none of them in the future. A cook who
    turns an order down says why (``cancel_reason``)."""
    if target is None and settled:
        target = OrderStatus.CANCELLED if rng.random() < 0.15 else OrderStatus.COMPLETED
    elif target is None:
        target = rng.choice(
            [OrderStatus.PLACED, OrderStatus.ACCEPTED, OrderStatus.READY]
        )

    stamps: dict[str, datetime | str] = {}
    at = placed
    if target is OrderStatus.CANCELLED:
        by = rng.choice([CancelledBy.CUSTOMER, CancelledBy.COOK])
        reasons = REJECT_REASONS
        if by is CancelledBy.COOK and rng.random() < 0.5:
            at += timedelta(minutes=rng.randint(5, 30))
            stamps["accepted_at"] = at
            reasons = CANCEL_REASONS
        stamps["cancelled_at"] = min(at + timedelta(minutes=rng.randint(5, 60)), now)
        stamps["cancelled_by"] = by.value
        if by is CancelledBy.COOK:
            stamps["cancel_reason"] = rng.choice(reasons)
        return target, stamps
    steps = [
        (OrderStatus.ACCEPTED, "accepted_at", (5, 30)),
        (OrderStatus.READY, "ready_at", (20, 75)),
        (OrderStatus.COMPLETED, "completed_at", (10, 45)),
    ]
    for status, column, (low, high) in steps:
        if target is OrderStatus.PLACED:
            break
        at += timedelta(minutes=rng.randint(low, high))
        stamps[column] = min(at, now)
        if status is target:
            break
    return target, stamps


async def _ensure_demo_orders(
    session: AsyncSession,
    customers: list[User],
    cooks: list[User],
    addresses: dict[uuid.UUID, Address],
    result: SeedResult,
) -> None:
    """The demo order history - only if no seeded account has any order yet
    (so never twice):

    * :data:`DEMO_ORDERS` settled orders over the last :data:`HISTORY_DAYS`
      days, skewed towards recent weeks;
    * :data:`DEMO_TODAY_ORDERS` completed earlier today in the showcase kitchen;
    * :data:`DEMO_OPEN_ORDERS` open ones from the last hours - the showcase
      kitchen's with :data:`SHOWCASE_OPEN_STATUSES`.

    The showcase kitchen (:data:`SHOWCASE_COOK`) gets the biggest share, so
    its cook dashboard is full. Buyers are mostly the customers, sometimes
    cooks ordering from colleagues (never from themselves). Each order takes
    1-3 active dishes of one cook at the dish's current price - the same
    snapshot rules as placing a real order - and is never older than either
    account.
    """
    account_ids = [user.id for user in [*customers, *cooks]]
    existing = await session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.customer_id.in_(account_ids))
    )
    if existing:
        result.orders_existing = existing
        return

    rng = random.Random(HISTORY_RANDOM_SEED)
    now = utcnow()
    today_start = datetime.combine(now.date(), datetime.min.time())
    menus = {cook.id: await _active_dishes(session, cook.id) for cook in cooks}
    showcase = next(cook for cook in cooks if cook.display_name == SHOWCASE_COOK)
    buyers = [*customers, *customers, *customers, *cooks]  # customers 3x as likely

    # (kind, forced status): "settled" | "today" | "open"; a forced status
    # means the showcase kitchen.
    plan: list[tuple[str, OrderStatus | None]] = [
        *(("settled", None) for _ in range(DEMO_ORDERS)),
        *(("today", OrderStatus.COMPLETED) for _ in range(DEMO_TODAY_ORDERS)),
        *(("open", status) for status in SHOWCASE_OPEN_STATUSES),
        *(
            ("open", None)
            for _ in range(DEMO_OPEN_ORDERS - len(SHOWCASE_OPEN_STATUSES))
        ),
    ]
    for kind, forced in plan:
        to_showcase = forced is not None or (
            kind == "settled" and rng.random() < SHOWCASE_SHARE
        )
        if to_showcase:
            cook = showcase
            buyer = rng.choice([b for b in buyers if b.id != showcase.id])
        else:
            buyer = rng.choice(buyers)
            cook = rng.choice([c for c in cooks if c.id != buyer.id and menus[c.id]])
        account_age = now - max(buyer.created_at, cook.created_at)
        if kind == "settled":  # at least a day old (settled), at most HISTORY_DAYS
            span_days = min(HISTORY_DAYS, account_age.total_seconds() / 86400)
            age = timedelta(days=max(1.0, rng.triangular(0, span_days, span_days / 4)))
        elif kind == "today":  # early enough today to be completed by now
            age = (now - today_start) * rng.uniform(0.3, 0.9)
        elif forced is not None:  # the showcase queue: fresh requests
            age = timedelta(minutes=rng.randint(5, SHOWCASE_OPEN_MINUTES))
        else:
            age = timedelta(minutes=rng.randint(10, OPEN_ORDER_HOURS * 60))
        placed = now - min(age, account_age)
        status, stamps = _demo_status(
            rng, placed, now, settled=kind != "open", target=forced
        )

        dishes = rng.sample(
            menus[cook.id], k=min(len(menus[cook.id]), rng.choice([1, 1, 2, 3]))
        )
        lines = [(dish, rng.choice([1, 1, 2, 2, 3, 4])) for dish in dishes]
        order = Order(
            customer_id=buyer.id,
            cook_id=cook.id,
            status=status.value,
            total=sum(dish.price * quantity for dish, quantity in lines),
            item_count=sum(quantity for _dish, quantity in lines),
            delivery_address=delivery_snapshot(addresses[buyer.id]),
            created_at=placed,
            updated_at=max(
                [placed, *(v for v in stamps.values() if isinstance(v, datetime))]
            ),
            **stamps,
        )
        session.add(order)
        await session.flush()
        for position, (dish, quantity) in enumerate(lines):
            session.add(
                OrderItem(
                    order_id=order.id,
                    dish_id=dish.id,
                    position=position,
                    name=dish.name,
                    unit_price=dish.price,
                    quantity=quantity,
                )
            )
        result.orders_created += 1


async def _ensure_demo_carts(
    session: AsyncSession, customers: list[User], cooks: list[User], result: SeedResult
) -> None:
    """An open cart for a couple of customers (skipped if they have one)."""
    for customer_index, cook_index, line_count in DEMO_CARTS:
        customer, cook = customers[customer_index], cooks[cook_index]
        if await session.scalar(select(Cart.id).where(Cart.user_id == customer.id)):
            continue
        cart = Cart(user_id=customer.id)
        session.add(cart)
        await session.flush()
        for offset, dish in enumerate(
            (await _active_dishes(session, cook.id))[:line_count]
        ):
            session.add(CartItem(cart_id=cart.id, dish_id=dish.id, quantity=offset + 1))
        result.carts_created += 1


async def _ensure_demo_favourites(
    session: AsyncSession,
    customers: list[User],
    cooks: list[User],
    now: datetime,
    result: SeedResult,
) -> None:
    """``DEMO_FAVOURITES`` for customers who have no favourites yet (a list
    edited in the UI is left alone). Matched by email, so a renamed account
    still gets its list; a dish deleted through the dashboard is skipped.
    Written directly - the demo's hidden favourite could not be saved through
    the API, which only takes available dishes."""
    cook_ids = {cook.email: cook.id for cook in cooks}
    for customer in customers:
        picks = next(
            (
                dishes
                for name, dishes in DEMO_FAVOURITES.items()
                if email_for(name) == customer.email
            ),
            (),
        )
        if not picks or await session.scalar(
            select(FavouriteDish.dish_id)
            .where(FavouriteDish.user_id == customer.id)
            .limit(1)
        ):
            continue
        for position, (cook_name, dish_name) in enumerate(picks):
            dish_id = await session.scalar(
                select(Dish.id).where(
                    Dish.cook_id == cook_ids[email_for(cook_name)],
                    Dish.name == dish_name,
                )
            )
            if dish_id is None:
                continue
            session.add(
                FavouriteDish(
                    user_id=customer.id,
                    dish_id=dish_id,
                    created_at=now
                    - timedelta(days=1 + position * FAVOURITE_SPACING_DAYS),
                )
            )
            result.favourites_created += 1


async def _ensure_demo_reviews(
    session: AsyncSession,
    customers: list[User],
    cooks: list[User],
    now: datetime,
    result: SeedResult,
) -> None:
    # Only dishes customers actually received (the API's own rule), and only
    # once: never while the seeded customers already have reviews.
    customer_ids = [customer.id for customer in customers]
    if await session.scalar(
        select(Review.id).where(Review.customer_id.in_(customer_ids)).limit(1)
    ):
        return
    showcase_cook = next(
        (cook.id for cook in cooks if cook.email == email_for(SHOWCASE_COOK)), None
    )
    showcase_customer = email_for(SHOWCASE_CUSTOMER)
    rows = (
        await session.execute(
            select(
                User.email,
                Order.customer_id,
                Order.cook_id,
                Order.id,
                Order.completed_at,
                Dish.id,
                Dish.name,
            )
            .join(User, User.id == Order.customer_id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Dish, Dish.id == OrderItem.dish_id)
            .where(Order.customer_id.in_(customer_ids), *full_cycle_conditions())
            # Stable order (not ids) so the fixed random seed gives the same reviews.
            .order_by(User.email, Dish.name, Order.completed_at.desc(), Order.id)
        )
    ).all()
    latest: dict[tuple[uuid.UUID, uuid.UUID], Any] = {}
    for row in rows:
        latest.setdefault((row[1], row[5]), row)  # first row = latest order
    showcase_rows = sorted(
        (row for row in latest.values() if row[0] == showcase_customer),
        key=lambda row: row[4],
        reverse=True,
    )
    keep_pending = {(row[1], row[5]) for row in showcase_rows[:SHOWCASE_UNREVIEWED]}

    rng = random.Random(REVIEW_RANDOM_SEED)
    stars = [rating for rating, _weight in RATING_WEIGHTS]
    weights = [weight for _rating, weight in RATING_WEIGHTS]
    for key, row in latest.items():
        _email, customer_id, cook_id, order_id, completed_at, dish_id, dish_name = row
        if key in keep_pending or rng.random() >= REVIEW_SHARE:
            continue
        rating = rng.choices(stars, weights=weights)[0]
        written = min(completed_at + timedelta(hours=rng.randint(1, 30)), now)
        review = Review(
            customer_id=customer_id,
            cook_id=cook_id,
            dish_id=dish_id,
            order_id=order_id,
            dish_name=dish_name,
            rating=rating,
            comment=rng.choice(REVIEW_COMMENTS[rating]),
            created_at=written,
            updated_at=written,
        )
        share = SHOWCASE_REPLY_SHARE if cook_id == showcase_cook else REPLY_SHARE
        if rng.random() < share:
            review.reply = rng.choice(REPLIES_HAPPY if rating >= 4 else REPLIES_SORRY)
            review.replied_at = min(written + timedelta(hours=rng.randint(1, 20)), now)
            review.updated_at = review.replied_at
            result.replies_created += 1
        session.add(review)
        result.reviews_created += 1


async def _ensure_demo_review_notifications(
    session: AsyncSession, customers: list[User], now: datetime, result: SeedResult
) -> None:
    # Replays the last NOTIFICATION_DAYS of seeded reviews through the live
    # notification rules, backdated - once: skipped while any review notice exists.
    if await session.scalar(
        select(Notification.id)
        .where(Notification.type == NotificationType.REVIEW_POSTED.value)
        .limit(1)
    ):
        return
    reviewer = aliased(User)
    kitchen = aliased(User)
    rows = (
        await session.execute(
            select(Review, reviewer.display_name, kitchen.display_name)
            .join(reviewer, reviewer.id == Review.customer_id)
            .join(kitchen, kitchen.id == Review.cook_id)
            .where(
                Review.customer_id.in_([customer.id for customer in customers]),
                Review.created_at >= now - timedelta(days=NOTIFICATION_DAYS),
            )
            .order_by(Review.created_at, Review.id)
        )
    ).all()
    for review, customer_name, cook_name in rows:
        await review_notifications.review_posted(
            session, review, customer_name=customer_name, at=review.created_at
        )
        result.notifications_created += 1
        if review.replied_at is not None:
            await review_notifications.review_replied(
                session, review, cook_name=cook_name, at=review.replied_at
            )
            result.notifications_created += 1
    await session.execute(
        update(Notification)
        .where(
            Notification.dedupe_key.like("review:%"),
            Notification.read_at.is_(None),
            Notification.created_at < now - timedelta(hours=UNREAD_HOURS),
        )
        .values(read_at=Notification.created_at)
        .execution_options(synchronize_session=False)
    )


async def _order_history_notifications(
    session: AsyncSession, orders: list[Order], names: dict[uuid.UUID, str | None]
) -> None:
    """Replay every step of ``orders`` through the live notification rules,
    each backdated to the moment it happened."""
    for order in orders:
        parties = {
            "cook_name": names.get(order.cook_id),
            "customer_name": names.get(order.customer_id),
        }
        await order_notifications.order_placed(
            session, order, at=order.created_at, **parties
        )
        steps: list[tuple[OrderStatus, OrderStatus, Party, datetime | None]] = [
            (OrderStatus.PLACED, OrderStatus.ACCEPTED, Party.COOK, order.accepted_at),
            (OrderStatus.ACCEPTED, OrderStatus.READY, Party.COOK, order.ready_at),
            (OrderStatus.READY, OrderStatus.COMPLETED, Party.CUSTOMER, order.completed_at),
        ]
        if order.cancelled_at is not None:
            steps.append(
                (
                    OrderStatus.ACCEPTED if order.accepted_at else OrderStatus.PLACED,
                    OrderStatus.CANCELLED,
                    Party(order.cancelled_by or Party.COOK.value),
                    order.cancelled_at,
                )
            )
        for previous, target, by, at in steps:
            if at is None:
                continue
            await order_notifications.status_changed(
                session,
                order,
                previous=previous,
                target=target,
                by=by,
                reason=order.cancel_reason,
                at=at,
                **parties,
            )


async def _ensure_demo_notifications(
    session: AsyncSession,
    admin: User | None,
    customers: list[User],
    cooks: list[User],
    now: datetime,
    result: SeedResult,
) -> None:
    """Inbox content for every panel - only while the seeded accounts have no
    order notifications yet (so never twice, and never on top of live ones).
    Every row carries a dedupe key, so even a partial earlier run cannot be
    duplicated."""
    accounts = [*customers, *cooks, *([admin] if admin else [])]
    account_ids = [user.id for user in accounts]
    existing = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id.in_(account_ids),
            Notification.type.like("order.%"),
        )
    )
    if existing:
        return
    before = await session.scalar(select(func.count()).select_from(Notification)) or 0

    # 1. The last days of orders, step by step.
    recent = (
        await session.scalars(
            select(Order)
            .where(
                Order.customer_id.in_(account_ids),
                Order.created_at >= now - timedelta(days=NOTIFICATION_DAYS),
            )
            .order_by(Order.created_at, Order.id)
        )
    ).all()
    names = {user.id: user.display_name for user in accounts}
    await _order_history_notifications(session, list(recent), names)

    # 2. Kitchens: their verification (the acceptance predates the inboxes).
    for cook in cooks:
        profile = await session.get(CookProfile, cook.id)
        if profile is not None and profile.verified_at is not None:
            await notifications.notify(
                session,
                recipient_id=cook.id,
                audience=Audience.COOK,
                kind=NotificationType.KITCHEN_VERIFIED,
                payload=NoPayload(),
                subject_id=cook.id,
                actor_id=profile.verified_by_id,
                dedupe_key=f"seed:kitchen:{cook.id}:verified",
                created_at=profile.verified_at,
            )

    # 3. Applications: the admins' review queue and the applicant's answer.
    for spec in APPLICATIONS:
        applicant = next(user for user in customers if user.display_name == spec.name)
        profile = await session.get(CookProfile, applicant.id)
        if profile is None or profile.status != spec.status.value:
            continue  # decided differently in the UI - leave it alone
        payload = CookApplicationPayload(
            applicant_name=applicant.display_name,
            headline=profile.headline,
            reason=profile.rejection_reason,
        )
        await notifications.notify_admins(
            session,
            kind=NotificationType.COOK_APPLICATION_SUBMITTED,
            payload=payload,
            subject_id=applicant.id,
            actor_id=applicant.id,
            dedupe_key=f"seed:cook_application:{applicant.id}:submitted",
            created_at=profile.submitted_at,
        )
        if spec.status is CookApplicationStatus.REJECTED:
            await notifications.notify(
                session,
                recipient_id=applicant.id,
                audience=Audience.ACCOUNT,
                kind=NotificationType.COOK_APPLICATION_REJECTED,
                payload=payload,
                subject_id=applicant.id,
                actor_id=profile.reviewed_by_id,
                dedupe_key=f"seed:cook_application:{applicant.id}:rejected",
                created_at=profile.reviewed_at,
            )
            await notifications.resolve(
                session,
                kind=NotificationType.COOK_APPLICATION_SUBMITTED,
                subject_id=applicant.id,
            )

    # Old news is read news: only the last UNREAD_HOURS stay unread.
    await session.execute(
        update(Notification)
        .where(
            Notification.recipient_id.in_(account_ids),
            Notification.read_at.is_(None),
            Notification.created_at < now - timedelta(hours=UNREAD_HOURS),
            # only what this function writes (order steps + seed: notices)
            or_(
                Notification.dedupe_key.like("order:%"),
                Notification.dedupe_key.like("seed:%"),
            ),
        )
        # (a plain column copy: date arithmetic is not portable SQL)
        .values(read_at=Notification.created_at)
        .execution_options(synchronize_session=False)
    )
    after = await session.scalar(select(func.count()).select_from(Notification)) or 0
    result.notifications_created = after - before


async def seed(*, random_passwords: bool = False) -> SeedResult:
    """Run the seed inside one transaction; safe to call repeatedly.

    Accounts get the role's :data:`DEMO_PASSWORDS` - unless
    ``random_passwords`` or the environment is production, where known
    passwords are never set (each account gets a fresh random one).
    """
    random_passwords = random_passwords or get_settings().is_production
    result = SeedResult(random_passwords=random_passwords)
    now = utcnow()
    cooks: list[User] = []
    customers: list[User] = []
    admin: User | None = None
    async with session_scope() as session:
        zones = await _ensure_zones(session, result)
        for name in ADMINS:
            email = email_for(name)
            secret = password_for("admin", random_passwords=random_passwords)
            admin, created = await _ensure_user(
                session,
                email=email,
                display_name=name,
                password=secret,
                roles=[ROLE_ADMIN],
                joined=joined_at(email, "admin", now),
            )
            result.users_created += created
            result.users_existing += not created
            result.accounts.append(
                SeedAccount(
                    email=email, password=secret, display_name=name, kind="admin"
                )
            )

        for spec in COOKS:
            email = email_for(spec.name)
            secret = password_for("cook", random_passwords=random_passwords)
            user, created = await _ensure_user(
                session,
                email=email,
                display_name=spec.name,
                password=secret,
                roles=[ROLE_CUSTOMER, ROLE_COOK],
                bio=spec.bio,
                area=spec.area,
                joined=joined_at(email, "cook", now),
            )
            cooks.append(user)
            result.users_created += created
            result.users_existing += not created
            await _ensure_cook_profile(session, user, spec, zones, admin)
            for dish_spec in spec.dishes:
                if await _ensure_dish(session, user.id, dish_spec):
                    result.dishes_created += 1
                else:
                    result.dishes_existing += 1
            result.accounts.append(
                SeedAccount(email=email, password=secret, display_name=spec.name, kind="cook")
            )

        for name in CUSTOMERS:
            email = email_for(name)
            secret = password_for("customer", random_passwords=random_passwords)
            user, created = await _ensure_user(
                session,
                email=email,
                display_name=name,
                password=secret,
                roles=[ROLE_CUSTOMER],
                joined=joined_at(email, "customer", now),
            )
            customers.append(user)
            result.users_created += created
            result.users_existing += not created
            result.accounts.append(
                SeedAccount(email=email, password=secret, display_name=name, kind="customer")
            )

        await session.flush()  # the history below queries the dishes just added
        addresses = await _ensure_addresses(session, customers, cooks, zones, result)
        await _ensure_demo_orders(session, customers, cooks, addresses, result)
        await _ensure_demo_carts(session, customers, cooks, result)
        await _ensure_demo_favourites(session, customers, cooks, now, result)
        await _ensure_demo_reviews(session, customers, cooks, now, result)
        await _ensure_applications(session, customers, zones, admin, now, result)
        await session.flush()
        await _ensure_demo_notifications(session, admin, customers, cooks, now, result)
        await _ensure_demo_review_notifications(session, customers, now, result)
    return result


def report(result: SeedResult, database: str) -> None:
    print(f"Plateboard seed - database: {database}")
    print(f"zones:   {result.zones_created} created, {result.zones_existing} kept")
    print(f"users:   {result.users_created} created, {result.users_existing} reused")
    print(f"dishes:  {result.dishes_created} created, {result.dishes_existing} kept")
    if result.orders_created:
        print(
            f"orders:  {result.orders_created} demo orders created (last {HISTORY_DAYS} days)"
        )
    else:
        print(f"orders:  {result.orders_existing} existing - no demo history added")
    print(f"carts:   {result.carts_created} demo carts created")
    print(f"favourites: {result.favourites_created} demo favourite dishes saved")
    print(f"reviews: {result.reviews_created} demo reviews, {result.replies_created} cook replies")
    print(f"address: {result.addresses_created} addresses created")
    print(
        f"cook applications: {result.applications_created} created "
        "(one pending review, one rejected)"
    )
    print(f"notifications: {result.notifications_created} created")
    print()
    starters = {
        "admin": (email_for(ADMINS[0]), "the platform"),
        "cook": (email_for(SHOWCASE_COOK), "the fullest demo kitchen"),
        "customer": (email_for(SHOWCASE_CUSTOMER), "orders, an open order and a bag"),
    }
    if result.random_passwords:
        print("Random passwords (production or --random-passwords): they are shown")
        print("only now and replace any earlier ones - note them down.")
    else:
        print("Demo logins - one password per role, the same on every run:")
        print()
        print(f"{'ROLE':<9} {'PASSWORD':<20} {'PANEL':<9} START WITH")
        for kind, (email, why) in starters.items():
            print(f"{kind:<9} {DEMO_PASSWORDS[kind]:<20} {PANELS[kind]:<9} {email} ({why})")
    print()
    print("Every seeded account:")
    print()
    width = max(len(account.email) for account in result.accounts) + 1
    print(f"{'EMAIL':<{width}} {'PASSWORD':<20} {'ROLE':<9} NAME")
    for account in sorted(result.accounts, key=lambda a: (a.kind, a.email)):
        print(
            f"{account.email:<{width}} {account.password:<20} "
            f"{account.kind:<9} {account.display_name}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="seed", description="Seed Plateboard with demo data (idempotent)."
    )
    parser.add_argument(
        "--random-passwords",
        action="store_true",
        help="give every account a fresh random password instead of the role's "
        "demo password (always on with ENVIRONMENT=production)",
    )
    args = parser.parse_args(argv)

    run_migrations()
    settings = get_settings()
    result = asyncio.run(seed(random_passwords=args.random_passwords))
    report(result, settings.DATABASE_URL)


if __name__ == "__main__":
    main()
