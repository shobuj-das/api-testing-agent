"""Notification orchestration — routes reports to configured channels."""
from __future__ import annotations

import logging
from typing import Protocol

from notifications.models import NotificationSeverity, TestSummary

logger = logging.getLogger("api_testing_agent")

class NotificationChannel(Protocol):
    def send(self, summary: TestSummary, *, severity: NotificationSeverity) -> bool: ...

class NotificationManager:
    """Aggregates channels and dispatches test summaries."""

    def __init__(self) -> None:
        self._channels: list[NotificationChannel] = []

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    def notify(self, summary: TestSummary) -> int:
        """Send to all channels. Returns count of successful deliveries."""
        if not self._channels:
            return 0
        severity = (
            NotificationSeverity.CRITICAL if summary.failed > 0
            else NotificationSeverity.INFO
        )
        successes = 0
        for channel in self._channels:
            try:
                if channel.send(summary, severity=severity):
                    successes += 1
            except Exception as exc:
                logger.warning(f"Notification channel failed: {exc}")
        return successes
