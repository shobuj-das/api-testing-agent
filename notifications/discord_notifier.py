"""Discord webhook notifier."""
from __future__ import annotations

import logging
from typing import Any

import requests

from notifications.models import NotificationSeverity, TestSummary

logger = logging.getLogger("api_testing_agent")

class DiscordNotifier:
    """Send structured test reports to a Discord webhook."""

    def __init__(self, webhook_url: str, *, mention_role: str | None = None) -> None:
        if not webhook_url:
            raise ValueError("Discord webhook URL is required.")
        self._webhook_url = webhook_url
        self._mention_role = mention_role

    def send(self, summary: TestSummary, *, severity: NotificationSeverity) -> bool:
        """Send formatted embed to Discord. Returns True on success."""
        color = {"info": 0x2ECC71, "warning": 0xF39C12, "critical": 0xE74C3C}[severity]
        status_emoji = "✅" if summary.failed == 0 else "❌"

        embed: dict[str, Any] = {
            "title": f"{status_emoji} API Test Report — {summary.project_name}",
            "color": color,
            "fields": [
                {"name": "Total", "value": str(summary.total_tests), "inline": True},
                {"name": "Passed", "value": str(summary.passed), "inline": True},
                {"name": "Failed", "value": str(summary.failed), "inline": True},
                {"name": "Errors", "value": str(summary.errors), "inline": True},
                {"name": "Pass Rate", "value": f"{summary.pass_rate:.1f}%", "inline": True},
            ],
        }
        # Add top 5 failures
        if summary.failures:
            failure_text = "\n".join(
                f"• `{f.test_id}` — {f.method} {f.endpoint} "
                f"({f.classification or 'unclassified'})"
                for f in summary.failures[:5]
            )
            embed["fields"].append({"name": "Top Failures", "value": failure_text})

        if summary.report_url:
            embed["fields"].append(
                {"name": "Full Report", "value": f"[View Report]({summary.report_url})"}
            )

        payload: dict[str, Any] = {"embeds": [embed]}
        if self._mention_role:
            payload["content"] = f"<@&{self._mention_role}>"

        try:
            resp = requests.post(self._webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Discord notification sent successfully.")
            return True
        except Exception as exc:
            logger.warning(f"Discord notification failed: {exc}")
            return False
