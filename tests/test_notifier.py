"""Tests for the notification system — toast and email."""

from unittest.mock import MagicMock, patch, call

import pytest

from src.notifications.notifier import Notifier


@pytest.fixture
def notifier_config():
    return {
        "notifications": {
            "email_to": "test@example.com",
            "email_from": "sender@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user",
            "smtp_password": "password123",
        },
    }


@pytest.fixture
def notifier(notifier_config):
    return Notifier(notifier_config)


@pytest.fixture
def notifier_no_email():
    return Notifier({"notifications": {}})


# ── Init ──────────────────────────────────────────────────────────────────

class TestNotifierInit:
    def test_reads_config(self, notifier):
        assert notifier.email_to == "test@example.com"
        assert notifier.smtp_host == "smtp.example.com"
        assert notifier.smtp_port == 587

    def test_defaults_when_no_config(self, notifier_no_email):
        assert notifier_no_email.email_to == "liam.bond@caseware.com"
        assert notifier_no_email.smtp_password == ""


# ── send_toast ────────────────────────────────────────────────────────────

class TestSendToast:
    def test_returns_true_on_success(self, notifier):
        """Mock winotify to test toast success path."""
        mock_notification = MagicMock()
        mock_audio = MagicMock()
        with patch.dict("sys.modules", {
            "winotify": MagicMock(Notification=MagicMock(return_value=mock_notification), audio=mock_audio),
        }):
            result = notifier.send_toast("Title", "Message")
        assert result is True

    def test_falls_back_to_powershell(self, notifier):
        """When winotify fails, try PowerShell."""
        import builtins
        original_import = builtins.__import__

        def selective_import(name, *args, **kwargs):
            if name == "winotify":
                raise ImportError("No winotify")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=selective_import):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = notifier.send_toast("Title", "Message")
        assert result is True

    def test_returns_false_on_all_failures(self, notifier):
        """When both winotify and PowerShell fail."""
        def raise_import(*args, **kwargs):
            raise ImportError("No winotify")

        with patch("builtins.__import__", side_effect=raise_import):
            with patch("subprocess.run", side_effect=Exception("PS failed")):
                result = notifier.send_toast("Title", "Message")
        assert result is False


# ── send_email ────────────────────────────────────────────────────────────

class TestSendEmail:
    def test_returns_false_when_no_password(self, notifier_no_email):
        result = notifier_no_email.send_email("Subject", "<p>Body</p>")
        assert result is False

    def test_sends_email_successfully(self, notifier):
        with patch("src.notifications.notifier.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            result = notifier.send_email("Subject", "<p>Body</p>")
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "password123")
        mock_server.sendmail.assert_called_once()

    def test_returns_false_on_smtp_error(self, notifier):
        with patch("src.notifications.notifier.smtplib.SMTP", side_effect=Exception("SMTP down")):
            result = notifier.send_email("Subject", "<p>Body</p>")
        assert result is False


# ── notify ────────────────────────────────────────────────────────────────

class TestNotify:
    def test_calls_toast_and_email(self, notifier):
        with patch.object(notifier, "send_toast") as mock_toast:
            with patch.object(notifier, "send_email") as mock_email:
                notifier.notify(
                    qualifying_count=5,
                    new_count=3,
                    near_miss_count=2,
                    report_path="output/reports/report_2026-03-22.html",
                    top_properties=[],
                )
        mock_toast.assert_called_once()
        mock_email.assert_called_once()

    def test_skips_email_when_no_password(self, notifier_no_email):
        with patch.object(notifier_no_email, "send_toast"):
            with patch.object(notifier_no_email, "send_email") as mock_email:
                notifier_no_email.notify(5, 3, 2, "report.html")
        mock_email.assert_not_called()

    def test_toast_title_includes_qualifying_count(self, notifier):
        with patch.object(notifier, "send_toast") as mock_toast:
            with patch.object(notifier, "send_email"):
                notifier.notify(10, 5, 3, "report.html")
        title = mock_toast.call_args[0][0]
        assert "10" in title
        assert "Qualifying" in title

    def test_toast_title_daily_update_when_zero_qualifying(self, notifier):
        with patch.object(notifier, "send_toast") as mock_toast:
            with patch.object(notifier, "send_email"):
                notifier.notify(0, 2, 1, "report.html")
        title = mock_toast.call_args[0][0]
        assert "Daily Update" in title


# ── _build_email_html ─────────────────────────────────────────────────────

class TestBuildEmailHtml:
    def test_includes_counts(self, notifier):
        html = notifier._build_email_html(5, 3, 2, "report.html", [])
        assert "5" in html
        assert "3" in html
        assert "2" in html

    def test_includes_top_properties(self, notifier):
        props = [
            {
                "address": "1 Test Road",
                "property_type": "terraced",
                "bedrooms": 2,
                "tenure": "freehold",
                "price": 175000,
                "url": "https://example.com",
                "_scores": {"total": 82},
            },
        ]
        html = notifier._build_email_html(1, 1, 0, "report.html", props)
        assert "1 Test Road" in html
        assert "175,000" in html
        assert "82" in html

    def test_limits_to_five_properties(self, notifier):
        props = [
            {"address": f"Prop {i}", "property_type": "flat", "bedrooms": 1, "tenure": "leasehold", "price": 100000 + i * 1000, "url": "#", "_scores": {"total": 50 + i}}
            for i in range(10)
        ]
        html = notifier._build_email_html(10, 5, 2, "report.html", props)
        # Only first 5 should appear
        assert "Prop 0" in html
        assert "Prop 4" in html
        assert "Prop 5" not in html

    def test_handles_empty_top_properties(self, notifier):
        html = notifier._build_email_html(0, 0, 0, "report.html", [])
        assert "Property Search Report" in html
