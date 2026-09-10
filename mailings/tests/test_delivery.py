from unittest.mock import patch

from django.test import SimpleTestCase

from mailings.delivery import (
    MAX_SEND_DELAY_SECONDS,
    MIN_SEND_DELAY_SECONDS,
    send_email,
)
from mailings.models import MailingMessage


class SendEmailTests(SimpleTestCase):
    @patch("mailings.delivery.logger.info")
    @patch("mailings.delivery.sleep")
    @patch("mailings.delivery.randint", return_value=7)
    def test_waits_for_random_delay_before_logging_without_message_content(
        self,
        mocked_randint,
        mocked_sleep,
        mocked_log,
    ):
        events = []
        mocked_sleep.side_effect = lambda delay: events.append(("sleep", delay))
        mocked_log.side_effect = lambda *args: events.append(("log", args))
        mailing = MailingMessage(
            external_id="mailing-001",
            user_id=42,
            email="private@example.com",
            subject="Private subject",
            message="Private message body",
        )

        send_email(mailing)

        mocked_randint.assert_called_once_with(
            MIN_SEND_DELAY_SECONDS,
            MAX_SEND_DELAY_SECONDS,
        )
        mocked_sleep.assert_called_once_with(7)
        mocked_log.assert_called_once_with(
            "Email sent: external_id=%s",
            "mailing-001",
        )
        self.assertEqual([event[0] for event in events], ["sleep", "log"])
        self.assertNotIn("private@example.com", repr(mocked_log.call_args))
        self.assertNotIn("Private message body", repr(mocked_log.call_args))
