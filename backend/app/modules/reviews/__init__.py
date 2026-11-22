# Deliberately empty (like notifications/__init__.py): dishes and cooks schemas
# import reviews.schemas for the rating on their cards, and importing the router
# here would lead back into dishes -> a circular import. app/api/router.py
# imports reviews.router directly.
