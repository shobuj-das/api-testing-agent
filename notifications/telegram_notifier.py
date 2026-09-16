"""Telegram Bot API notifier."""
from __future__ import annotations

import logging

import requests

from notifications.models import NotificationSeverity, TestSummary

logger = logging.getLogger("api_testing_agent")

class TelegramNotifier:
    """Send structured test reports to a Telegram chat via Bot API."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot_token and chat_id are both required.")
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, summary: TestSummary, *, severity: NotificationSeverity) -> bool:
        """Send formatted message to Telegram. Returns True on success."""
        emoji = "✅" if summary.failed == 0 else "🚨"
        lines = [
            f"{emoji} *API Test Report — {self._escape(summary.project_name)}*",
            "",
            f"📊 Total: {summary.total_tests} | ✅ Passed: {summary.passed} | "
            f"❌ Failed: {summary.failed} | ⚠️ Errors: {summary.errors}",
            f"📈 Pass Rate: {summary.pass_rate:.1f}%",
        ]
        if summary.failures:
            lines.append("\n*Top Failures:*")
            for f in summary.failures[:5]:
                lines.append(
                    f"• `{self._escape(f.test_id)}` — {f.method} {self._escape(f.endpoint)} "
                    f"({self._escape(f.classification or 'unclassified')})"
                )
        if summary.report_url:
            lines.append(f"\n[Full Report]({summary.report_url})")

        text = "\n".join(lines)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(self._api_url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Telegram notification sent successfully.")
            return True
        except Exception as exc:
            logger.warning(f"Telegram notification failed: {exc}")
            return False

    @staticmethod
    def _escape(text: str) -> str:
        """Escape Telegram MarkdownV2 special characters."""
        for char in r"\_*[]()~`>#+-=|{}.!":
            text = text.replace(char, f"\\{char}")
        return text
