"""Delivery channels beyond the in-app inbox (Task 22).

In-app delivery is the notification row itself and is always on. Other
channels (push, e-mail, WhatsApp, SMS) plug in here behind one small
interface, so no vendor is hardwired. A channel receives the stored
notification and its recipient after the row is committed; failures are
logged and never block other channels or the in-app row.

To add a provider: implement `NotificationChannel`, register it in
`CHANNELS`, configure its credentials through environment settings, and
list its name in NOTIFICATION_CHANNELS.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.models.notifications import Notification
from app.models.user import User

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    name: str

    def deliver(self, notification: Notification, user: User) -> None: ...


class LogChannel:
    """Writes a log line per delivery. For development and for wiring tests.

    Only ids and the kind are logged: titles can name vehicles or drivers.
    """

    name = "log"

    def deliver(self, notification: Notification, user: User) -> None:
        logger.info(
            "notification_delivered",
            extra={
                "channel": self.name,
                "notification_id": str(notification.id),
                "user_id": str(user.id),
                "kind": notification.kind,
                "severity": notification.severity.value,
            },
        )


CHANNELS: dict[str, NotificationChannel] = {"log": LogChannel()}


def configured(names: str) -> list[NotificationChannel]:
    """Channels listed in settings; unknown names are reported and skipped."""
    selected: list[NotificationChannel] = []
    for name in (n.strip() for n in names.split(",")):
        if not name:
            continue
        channel = CHANNELS.get(name)
        if channel is None:
            logger.warning("notification_channel_unknown", extra={"channel": name})
            continue
        selected.append(channel)
    return selected
