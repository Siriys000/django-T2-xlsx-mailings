from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from mailings.delivery import MAX_DELIVERY_ATTEMPTS
from mailings.models import MailingMessage


class RetryMailingsCommandTests(TestCase):
    @staticmethod
    def create_mailing(external_id, **overrides):
        values = {
            "external_id": external_id,
            "user_id": 42,
            "email": f"{external_id}@example.com",
            "subject": "Subject",
            "message": "Message",
        }
        values.update(overrides)
        return MailingMessage.objects.create(**values)

    @patch("mailings.delivery.send_email")
    def test_retries_pending_and_failed_messages_but_skips_sent(
        self, mocked_send_email
    ):
        pending = self.create_mailing("pending")
        failed = self.create_mailing(
            "failed",
            delivery_status=MailingMessage.DeliveryStatus.FAILED,
            delivery_attempts=MAX_DELIVERY_ATTEMPTS,
            last_delivery_error="RuntimeError",
        )
        sent = self.create_mailing(
            "sent",
            delivery_status=MailingMessage.DeliveryStatus.SENT,
            delivery_attempts=1,
            sent_at=timezone.now(),
        )
        stdout = StringIO()

        call_command("retry_mailings", stdout=stdout)

        pending.refresh_from_db()
        failed.refresh_from_db()
        sent.refresh_from_db()
        self.assertCountEqual(
            [call.args[0].external_id for call in mocked_send_email.call_args_list],
            ["pending", "failed"],
        )
        self.assertEqual(
            pending.delivery_status,
            MailingMessage.DeliveryStatus.SENT,
        )
        self.assertEqual(pending.delivery_attempts, 1)
        self.assertEqual(failed.delivery_status, MailingMessage.DeliveryStatus.SENT)
        self.assertEqual(failed.delivery_attempts, MAX_DELIVERY_ATTEMPTS + 1)
        self.assertEqual(sent.delivery_attempts, 1)
        self.assertIn(
            "Retry completed: processed=2, sent=2, failed=0, attempts=2, retries=0",
            stdout.getvalue(),
        )

    @patch("mailings.delivery.send_email", side_effect=RuntimeError("unavailable"))
    def test_failed_retry_remains_available_for_a_later_run(self, mocked_send_email):
        mailing = self.create_mailing("mailing-001")
        stdout = StringIO()

        with patch("mailings.delivery.logger.warning"):
            call_command("retry_mailings", stdout=stdout)

        mailing.refresh_from_db()
        self.assertEqual(mocked_send_email.call_count, MAX_DELIVERY_ATTEMPTS)
        self.assertEqual(
            mailing.delivery_status,
            MailingMessage.DeliveryStatus.FAILED,
        )
        self.assertEqual(mailing.delivery_attempts, MAX_DELIVERY_ATTEMPTS)
        self.assertIn(
            "processed=1, sent=0, failed=1, attempts=3, retries=2",
            stdout.getvalue(),
        )

        mocked_send_email.reset_mock()
        mocked_send_email.side_effect = None
        call_command("retry_mailings", stdout=StringIO())

        mailing.refresh_from_db()
        self.assertEqual(
            mailing.delivery_status,
            MailingMessage.DeliveryStatus.SENT,
        )
        self.assertEqual(mailing.delivery_attempts, MAX_DELIVERY_ATTEMPTS + 1)
        mocked_send_email.assert_called_once()

    @patch("mailings.delivery.send_email")
    def test_reports_zero_when_nothing_is_retryable(self, mocked_send_email):
        stdout = StringIO()

        call_command("retry_mailings", stdout=stdout)

        mocked_send_email.assert_not_called()
        self.assertIn(
            "processed=0, sent=0, failed=0, attempts=0, retries=0",
            stdout.getvalue(),
        )
