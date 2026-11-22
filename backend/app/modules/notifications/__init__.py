"""In-app notifications: one inbox per panel (account, cook, admin).

* ``models.Notification`` - one row per recipient and event (the panel it
  belongs to, what happened, what it is about, a data snapshot, read state)
* ``catalog`` - every notification type: payload model, subject kind, and
  the text per audience (rendered at read time)
* ``service.notify`` / ``service.notify_admins`` / ``service.resolve`` - what
  feature services call inside their own transaction (no commit of their own)
* ``router.notification_router`` - ``/api/me/notifications`` (list, unread
  counts, mark read / unread / all read, dismiss)

Unlike the other feature packages, this ``__init__`` deliberately imports
nothing: the auth, cooks, admin and orders *services* import
``notifications.service``, and pulling the HTTP router in here would import
``auth.dependencies`` -> ``auth.service`` -> back into this package (a cycle).
``app/api/router.py`` imports ``notifications.router`` directly instead.

The model is registered for Alembic through ``app.models``.
"""
