"""Email and Windows toast notifications for daily report."""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)


class Notifier:
    """Send email + Windows toast notifications."""

    def __init__(self, config: dict):
        self.config = config
        notif_cfg = config.get("notifications", {})
        self.email_to = notif_cfg.get("email_to", "liam.bond@caseware.com")
        self.email_from = notif_cfg.get("email_from", "")
        self.smtp_host = notif_cfg.get("smtp_host", "smtp.gmail.com")
        self.smtp_port = notif_cfg.get("smtp_port", 587)
        self.smtp_user = notif_cfg.get("smtp_user", "")
        self.smtp_password = notif_cfg.get("smtp_password", "")

    def send_toast(self, title: str, message: str, duration: int = 10) -> bool:
        """Show a Windows 10/11 toast notification.

        Tries winotify first, then falls back to PowerShell.
        """
        # Try winotify (works on Python 3.12+)
        try:
            from winotify import Notification, audio
            toast = Notification(
                app_id="Property Search",
                title=title,
                msg=message,
                duration="long",
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
            logger.info(f"Toast notification sent: {title}")
            return True
        except Exception as e:
            logger.debug(f"winotify failed: {e}, trying PowerShell")

        # Fallback: PowerShell BurntToast / Windows.UI.Notifications
        try:
            import subprocess
            ps_script = (
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null;"
                f"$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02;"
                f"$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template);"
                f"$text = $xml.GetElementsByTagName('text');"
                f"$text[0].AppendChild($xml.CreateTextNode('{title.replace(chr(39), '')}')) | Out-Null;"
                f"$text[1].AppendChild($xml.CreateTextNode('{message.replace(chr(39), '')}')) | Out-Null;"
                f"$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
                f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Property Search').Show($toast);"
            )
            subprocess.run(
                ["powershell", "-WindowStyle", "Hidden", "-Command", ps_script],
                capture_output=True, timeout=10
            )
            logger.info(f"Toast sent via PowerShell: {title}")
            return True
        except Exception as e:
            logger.warning(f"Toast notification failed: {e}")
            return False

    def send_email(
        self,
        subject: str,
        body_html: str,
        report_path: str | None = None,
    ) -> bool:
        """Send an HTML email. Returns True on success."""
        if not self.smtp_password:
            logger.warning("Email not configured — skipping (set smtp_password in notifications config)")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.email_from or self.smtp_user
            msg["To"] = self.email_to

            # Plain text fallback
            plain = f"Property Search Report\n\n{subject}\n\nOpen the attached report for details."
            msg.attach(MIMEText(plain, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(msg["From"], [self.email_to], msg.as_string())

            logger.info(f"Email sent to {self.email_to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email failed: {e}")
            return False

    def notify(
        self,
        qualifying_count: int,
        new_count: int,
        near_miss_count: int,
        report_path: str,
        top_properties: list[dict] | None = None,
    ) -> None:
        """Send all notifications for a daily run."""

        # Build summary text
        if qualifying_count > 0:
            toast_title = f"Property Search — {qualifying_count} Qualifying"
            toast_msg = (
                f"{new_count} new today | {qualifying_count} pass all gates | "
                f"{near_miss_count} near misses"
            )
        else:
            toast_title = "Property Search — Daily Update"
            toast_msg = (
                f"{new_count} new today | {near_miss_count} near misses"
            )

        # Toast notification
        self.send_toast(toast_title, toast_msg)

        # Email
        if self.smtp_password:
            html = self._build_email_html(
                qualifying_count, new_count, near_miss_count,
                report_path, top_properties or []
            )
            subject = toast_title
            self.send_email(subject, html, report_path)
        else:
            logger.info("Email notifications disabled — configure smtp_password in notifications config.")

    def _build_email_html(
        self,
        qualifying_count: int,
        new_count: int,
        near_miss_count: int,
        report_path: str,
        top_properties: list[dict],
    ) -> str:
        """Build a compact HTML email body."""
        report_filename = Path(report_path).name

        props_html = ""
        for prop in top_properties[:5]:
            scores = prop.get("_scores") or {}
            total = scores.get("total", "?")
            props_html += f"""
            <tr>
              <td style="padding:8px;border-bottom:1px solid #333;">
                <strong>{prop.get('address', 'Unknown')}</strong><br>
                <small style="color:#aaa;">{prop.get('property_type','?')} · {prop.get('bedrooms','?')} bed · {prop.get('tenure','?')}</small>
              </td>
              <td style="padding:8px;border-bottom:1px solid #333;text-align:right;font-weight:bold;">
                £{prop.get('price',0):,}
              </td>
              <td style="padding:8px;border-bottom:1px solid #333;text-align:center;color:#34d399;font-weight:bold;">
                {total}/100
              </td>
              <td style="padding:8px;border-bottom:1px solid #333;">
                <a href="{prop.get('url','#')}" style="color:#6c8cff;">View</a>
              </td>
            </tr>"""

        return f"""
        <html>
        <body style="background:#0f1117;color:#e1e4ed;font-family:sans-serif;padding:20px;max-width:600px;">
          <h2 style="color:#34d399;">Property Search Report</h2>
          <table style="width:100%;background:#1a1d27;border-radius:8px;padding:16px;margin-bottom:16px;">
            <tr>
              <td style="padding:8px;text-align:center;">
                <div style="font-size:2rem;font-weight:700;color:#34d399;">{qualifying_count}</div>
                <div style="color:#8b8fa3;font-size:0.75rem;text-transform:uppercase;">Qualifying</div>
              </td>
              <td style="padding:8px;text-align:center;">
                <div style="font-size:2rem;font-weight:700;color:#fbbf24;">{new_count}</div>
                <div style="color:#8b8fa3;font-size:0.75rem;text-transform:uppercase;">New Today</div>
              </td>
              <td style="padding:8px;text-align:center;">
                <div style="font-size:2rem;font-weight:700;">{near_miss_count}</div>
                <div style="color:#8b8fa3;font-size:0.75rem;text-transform:uppercase;">Near Misses</div>
              </td>
            </tr>
          </table>
          {"<h3>Top Qualifying Properties</h3><table style='width:100%;background:#1a1d27;border-radius:8px;'>" + props_html + "</table>" if top_properties else ""}
          <p style="color:#8b8fa3;font-size:0.85rem;margin-top:16px;">
            Full report saved: {report_filename}<br>
            Open it on your PC to view all {qualifying_count + near_miss_count} properties.
          </p>
        </body>
        </html>"""
