"""Public menu text search (``GET /api/dishes?q=``).

Acceptance rules under test:

* every word of ``q`` must appear - in any order - in the dish's name, its
  description or one of its ingredients (words ANDed, fields ORed);
* matching is substring-based and accent/case-insensitive on *both* sides
  (``svickova`` finds ``Svíčková``, ``SVÍČKOVÁ`` too), with typed ``%``/``_``
  kept literal;
* search composes with every other filter, keeps newest-first order and exact
  totals, never surfaces deactivated dishes, and is bounded (120 chars, 8 words).
"""

from __future__ import annotations

import pytest

from app.shared.text import fold_text, search_terms
from tests.test_dish_filters import names

MENU = (
    # name, description, ingredients, dietary tags, price
    ("Svíčková na smetaně", "Marinated beef in a cream sauce.", ["beef", "cream", "lingonberries"], [], 1400),
    ("Jollof Rice", "Smoky one-pot rice, long-reduced tomato base.", ["long grain rice", "tomatoes", "scotch bonnet"], ["vegan"], 750),
    ("Garden plate", None, ["jalapeño", "lettuce"], ["vegan"], 600),
    ("Chicken Katsu Curry", "Panko cutlet under a mild curry.", ["chicken", "panko", "curry roux"], [], 1050),
    ("Smoky Aubergine", "Charred, smoky and mashed with tomato.", ["aubergine", "tomato"], ["vegan"], 650),
    ("Fifty 50_50 Friday", "Half-price 100% chicken.", ["chicken"], [], 500),
)


@pytest.fixture
async def menu(accounts):
    """A real cook posts MENU through the API (so stored values are exactly
    what production stores), plus one deactivated smoky dish."""
    await accounts.cook()
    for name, description, ingredients, tags, price in MENU:
        created = await accounts.client.post(
            "/api/me/dishes",
            json={
                "name": name,
                "description": description,
                "price": price,
                "portions": 4,
                "ingredients": ingredients,
                "dietary_tags": tags,
            },
        )
        assert created.status_code == 201, created.text
    hidden = await accounts.client.post(
        "/api/me/dishes",
        json={"name": "Retired smoky stew", "price": 700, "portions": 2},
    )
    await accounts.client.patch(
        f"/api/me/dishes/{hidden.json()['id']}", json={"active": False}
    )
    return accounts.client


# --- the folding helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("Svíčková", "svickova"),
        ("SVÍČKOVÁ NA SMETANĚ", "svickova na smetane"),
        ("jalapeño", "jalapeno"),
        ("Straße", "strasse"),  # casefold, not just lower
        ("ﬁsh", "fish"),  # compatibility ligature
        (None, None),
    ],
)
def test_fold_text(raw: str | None, folded: str | None) -> None:
    assert fold_text(raw) == folded


def test_search_terms_split_fold_and_dedupe() -> None:
    assert search_terms("  Smoky  TOMATO smoky\tRice ") == ["smoky", "tomato", "rice"]
    assert search_terms("   ") == []
    assert search_terms(None) == []


# --- where a word may match ---------------------------------------------------------


async def test_matches_the_name(menu) -> None:
    assert await names(menu, q="katsu") == {"Chicken Katsu Curry"}


async def test_matches_the_description(menu) -> None:
    # "cutlet" only appears in the katsu description.
    assert await names(menu, q="cutlet") == {"Chicken Katsu Curry"}


async def test_matches_an_ingredient(menu) -> None:
    # "lingonberries" is only an ingredient; "bonnet" is part of one.
    assert await names(menu, q="lingonberries") == {"Svíčková na smetaně"}
    assert await names(menu, q="bonnet") == {"Jollof Rice"}


async def test_dishes_without_description_still_searchable(menu) -> None:
    assert await names(menu, q="lettuce") == {"Garden plate"}


# --- multi-word, accents, case, wildcards ---------------------------------------------


async def test_every_word_must_match_in_any_order_and_field(menu) -> None:
    # smoky: Jollof (description) + Aubergine (name/description);
    # tomato: both - but "rice" narrows to Jollof, in any word order.
    assert await names(menu, q="smoky tomato") == {"Jollof Rice", "Smoky Aubergine"}
    assert await names(menu, q="rice smoky") == {"Jollof Rice"}
    # Words can come from different fields of the same dish.
    assert await names(menu, q="panko mild chicken") == {"Chicken Katsu Curry"}
    assert await names(menu, q="smoky lettuce") == set()


async def test_accent_and_case_insensitive_both_ways(menu) -> None:
    for query in ("svickova", "SVÍČKOVÁ", "Svíčková", "smetane"):
        assert await names(menu, q=query) == {"Svíčková na smetaně"}, query
    # ...and an accented stored ingredient matches an unaccented query.
    assert await names(menu, q="JALAPENO") == {"Garden plate"}


async def test_typed_wildcards_are_literal(menu) -> None:
    assert await names(menu, q="50_50") == {"Fifty 50_50 Friday"}
    assert await names(menu, q="100%") == {"Fifty 50_50 Friday"}
    assert await names(menu, q="_") == {"Fifty 50_50 Friday"}  # not "any char"
    assert await names(menu, q="%") == {"Fifty 50_50 Friday"}


async def test_blank_search_is_no_search(menu) -> None:
    assert len(await names(menu, q="   ")) == len(MENU)


# --- composition and limits -------------------------------------------------------------


async def test_search_combines_with_filters(menu) -> None:
    assert await names(menu, q="tomato", dietary_tag="vegan", max_price=700) == {
        "Smoky Aubergine"
    }


async def test_search_never_finds_deactivated_dishes(menu) -> None:
    assert "Retired smoky stew" not in await names(menu, q="smoky")


async def test_search_results_stay_newest_first(menu) -> None:
    body = (await menu.get("/api/dishes", params={"q": "smoky"})).json()
    # Smoky Aubergine was posted after Jollof Rice.
    assert [dish["name"] for dish in body["items"]] == ["Smoky Aubergine", "Jollof Rice"]


async def test_search_is_bounded(menu) -> None:
    nine_words = " ".join(f"w{i}" for i in range(9))
    too_many = await menu.get("/api/dishes", params={"q": nine_words})
    assert too_many.status_code == 422
    assert too_many.json()["error"]["details"][0]["field"] == "q"
    eight = await menu.get("/api/dishes", params={"q": " ".join(["rice"] * 8 + ["x"])})
    assert eight.status_code == 200  # duplicates collapse: 2 distinct words
    too_long = await menu.get("/api/dishes", params={"q": "x" * 121})
    assert too_long.status_code == 422
