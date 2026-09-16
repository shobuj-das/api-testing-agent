"""Unit tests for the notification system."""
import pytest
from notifications.models import NotificationSeverity, TestSummary, FailureSummary
from notifications.manager import NotificationManager

def test_notification_models():
    """Test notification models validation."""
    summary = TestSummary(
        project_name="Test Project",
        total_tests=10,
        passed=8,
        failed=2,
        errors=0,
        pass_rate=80.0,
        failures=[
            FailureSummary(
                test_id="test_1",
                title="Test 1",
                endpoint="/api/v1/users",
                method="GET",
                expected_status=200,
                actual_status=500
            )
        ]
    )
    assert summary.total_tests == 10
    assert summary.failures[0].test_id == "test_1"

class DummyNotifier:
    def __init__(self):
        self.sent = False
        self.summary = None

    def send(self, summary: TestSummary, *, severity: NotificationSeverity) -> bool:
        self.sent = True
        self.summary = summary
        return True

def test_notification_manager():
    """Test the notification manager channel aggregation."""
    manager = NotificationManager()
    channel = DummyNotifier()
    manager.add_channel(channel)
    
    summary = TestSummary(
        project_name="Test Project",
        total_tests=1,
        passed=0,
        failed=1,
        errors=0,
        pass_rate=0.0
    )
    
    delivered = manager.notify(summary)
    assert delivered == 1
    assert channel.sent
    assert channel.summary.project_name == "Test Project"
