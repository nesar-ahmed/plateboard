"""Seed the Plateboard database with demo data: 10 cooks, 40 dishes, 5 customers.

Run from ``backend/``::

    uv run python scripts/seed.py

What it does:

* ensures the schema is at head (runs the Alembic migrations, like the server
  entry point does),
* creates (or reuses) the fictional accounts below - every email is
  ``first.last@example.com``, every password is freshly random *each run* and
  printed, so the printed credentials always work. Existing seeded accounts
  get their password reset to the newly generated one - that is what makes
  re-running safe *and* useful (you can always log in with what you see).
* creates dishes missing from the seed list, keyed on ``(cook, name)`` -
  dishes that already exist are left untouched, so edits or deactivations
  made through the dashboard survive a re-run.

All names are invented; any resemblance to real persons is coincidental.
"""

from __future__ import annotations

import asyncio
import dataclasses
import secrets
import sys
import unicodedata
import uuid
from pathlib import Path

# Import `app.*` whether this runs as `python scripts/seed.py` (sys.path[0]
# would otherwise be scripts/) or as `python -m scripts.seed`.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.models import ROLE_COOK, ROLE_CUSTOMER, CookProfile, User
from app.api.auth.security import hash_password
from app.api.dishes.models import ALLERGEN_VALUES, Dish
from app.core.db import session_scope
from app.main import run_migrations


@dataclasses.dataclass(frozen=True)
class DishSpec:
    name: str
    description: str
    price: int  # minor units
    portions: int
    ingredients: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()  # tokens from app.api.dishes.models.Allergen
    dietary_tags: tuple[str, ...] = ()
    active: bool = True


@dataclasses.dataclass(frozen=True)
class CookSpec:
    name: str
    headline: str
    area: str
    bio: str
    specialties: tuple[str, ...]
    dishes: tuple[DishSpec, ...]


# 10 cooks x 4 dishes = 40 dishes; two are deactivated on purpose so the
# dashboard has something to reactivate and the public menu something to hide.
COOKS: tuple[CookSpec, ...] = (
    CookSpec(
        name="Nadia Rahman",
        headline="Biryani, reinvented one pot at a time",
        area="Dhanmondi, Dhaka",
        bio="Third-generation home cook chasing the perfect crunchy alu.",
        specialties=("biryani", "korma"),
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


@dataclasses.dataclass
class SeedAccount:
    email: str
    password: str
    display_name: str
    kind: str  # "cook" | "customer"

    @property
    def line(self) -> str:
        return f"{self.email:<28} {self.password:<16} {self.display_name}"


@dataclasses.dataclass
class SeedResult:
    accounts: list[SeedAccount] = dataclasses.field(default_factory=list)
    users_created: int = 0
    users_existing: int = 0
    dishes_created: int = 0
    dishes_existing: int = 0


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
    """Fresh random credential for every run (>= 8 chars per auth rules)."""
    return secrets.token_urlsafe(9)


async def _ensure_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    password: str,
    roles: list[str],
    bio: str | None = None,
    area: str | None = None,
) -> tuple[User, bool]:
    """Create the account, or reuse it with a reset password.

    Returns ``(user, created)``. Password reset is deliberate: the run prints
    new credentials, so the printed ones must always work.
    """
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        existing.display_name = display_name
        existing.bio = bio if bio is not None else existing.bio
        existing.area = area if area is not None else existing.area
        # Roles grow, never replace (mirrors the become-a-cook rule).
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
    )
    session.add(user)
    # The UUID primary key is filled in at INSERT time; the cook profile and
    # dish rows below use it as an FK, so flush now rather than at commit.
    await session.flush()
    return user, True


async def _ensure_cook_profile(
    session: AsyncSession, user: User, spec: CookSpec
) -> None:
    profile = await session.get(CookProfile, user.id)
    if profile is not None:
        return  # leave dashboard edits alone
    session.add(
        CookProfile(
            user_id=user.id, headline=spec.headline, specialties=list(spec.specialties)
        )
    )


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


async def seed() -> SeedResult:
    """Run the seed inside one transaction; safe to call repeatedly."""
    result = SeedResult()
    async with session_scope() as session:
        for spec in COOKS:
            email = email_for(spec.name)
            secret = generate_password()
            user, created = await _ensure_user(
                session,
                email=email,
                display_name=spec.name,
                password=secret,
                roles=[ROLE_CUSTOMER, ROLE_COOK],
                bio=spec.bio,
                area=spec.area,
            )
            result.users_created += created
            result.users_existing += not created
            await _ensure_cook_profile(session, user, spec)
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
            secret = generate_password()
            user, created = await _ensure_user(
                session,
                email=email,
                display_name=name,
                password=secret,
                roles=[ROLE_CUSTOMER],
            )
            result.users_created += created
            result.users_existing += not created
            result.accounts.append(
                SeedAccount(email=email, password=secret, display_name=name, kind="customer")
            )
    return result


def report(result: SeedResult, database: str) -> None:
    print(f"Plateboard seed - database: {database}")
    print(f"users:   {result.users_created} created, {result.users_existing} reused")
    print(f"dishes:  {result.dishes_created} created, {result.dishes_existing} kept")
    print()
    print("Login with any of these (passwords are regenerated every run:")
    print("and applied to the account, so they always work):")
    print()
    print(f"{'EMAIL':<28} {'PASSWORD':<16} NAME")
    for account in sorted(result.accounts, key=lambda a: (a.kind, a.email)):
        print(account.line)


def main() -> None:
    from app.core.config import get_settings

    run_migrations()
    settings = get_settings()
    result = asyncio.run(seed())
    report(result, settings.DATABASE_URL)


if __name__ == "__main__":
    main()
