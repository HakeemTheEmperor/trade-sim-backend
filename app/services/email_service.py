import html
import logging

import requests

from ..integrations.providers import Brevo
from ..models.email_otp import OTP_TTL_MINUTES

logger = logging.getLogger(__name__)

# Outbound cap. This one sits in the request/response path of signup, so it's
# tighter than the scheduler's 15s: a slow provider must not hold a user's
# signup open.
REQUEST_TIMEOUT_SECONDS = 10


class EmailService:
    """Transactional email via Brevo's REST API.

    Two deliberate properties:

    - **Never raises.** Every send returns a bool and swallows provider errors
      after logging them. A Brevo outage must not turn signup into a 500 — the
      account is already created and the user can hit "Resend code".
    - **Degrades to the log.** With no BREVO_API_KEY configured (local dev, CI)
      the message and the code are written to the log instead of being sent, so
      the whole verification flow is exercisable without a provider account.
    """

    def _dev_mode(self):
        return not Brevo.api_key()

    def send(self, to_email, to_name, subject, html_body, log_hint=None):
        """Send one email. Returns True if it was accepted (or dev-logged)."""
        if self._dev_mode():
            # log_hint carries the OTP so it's usable in dev. Only ever reached
            # when no API key is set, i.e. never in a configured deployment.
            logger.warning(
                "BREVO_API_KEY not set; email NOT sent. to=%s subject=%r %s",
                to_email, subject, log_hint or "",
            )
            return True

        sender = Brevo.sender()
        if not sender["email"]:
            logger.error("BREVO_SENDER_EMAIL is not set; cannot send %r to %s", subject, to_email)
            return False

        try:
            response = requests.post(
                Brevo.send_email_url(),
                headers={
                    "api-key": Brevo.api_key(),
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "sender": sender,
                    "to": [{"email": to_email, "name": to_name}],
                    "subject": subject,
                    "htmlContent": html_body,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            logger.info("Sent %r to %s", subject, to_email)
            return True
        except requests.RequestException:
            # Log the failure, not the body: a Brevo error response can echo the
            # payload back, and the payload contains the OTP.
            logger.exception("Failed to send %r to %s", subject, to_email)
            return False

    def send_verification_code(self, user, code):
        subject = "Your iMockMarket verification code"
        # Escaped because it lands in an HTML document; a name is user-supplied
        # and would otherwise be an injection point into the email body.
        first_name = html.escape(user.first_name or "there")
        body = f"""
        <div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;color:#111">
          <h2 style="margin:0 0 16px">Verify your email</h2>
          <p style="margin:0 0 16px">Hi {first_name}, use this code to activate your iMockMarket account:</p>
          <p style="font-size:32px;font-weight:bold;letter-spacing:8px;margin:0 0 16px">{code}</p>
          <p style="margin:0 0 16px;color:#555">The code expires in {OTP_TTL_MINUTES} minutes and can only be used once.</p>
          <p style="margin:0;color:#555;font-size:13px">If you didn't create an account, you can safely ignore this email.</p>
        </div>
        """
        return self.send(
            to_email=user.email,
            to_name=f"{user.first_name} {user.last_name}".strip(),
            subject=subject,
            html_body=body,
            log_hint=f"code={code}",
        )
