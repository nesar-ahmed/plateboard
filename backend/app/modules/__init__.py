"""Domain modules: one package per feature, each owning its own
router/schemas/models/service. The HTTP wiring in ``app.api`` composes these;
migrations import the models through ``app.models``."""
