from threading import Barrier, BrokenBarrierError
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from mailings.delivery import (
    MAX_DELIVERY_ATTEMPTS,
    MAX_SEND_DELAY_SECONDS,
    MIN_SEND_DELAY_SECONDS,
    deliver_batch,
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


class DeliverBatchTests(TestCase):
    @staticmethod
    def create_mailing(external_id="mailing-001"):
        return MailingMessage.objects.create(
            external_id=external_id,
            user_id=42,
            email="recipient@example.com",
            subject="Subject",
            message="Message",
        )

    @patch("mailings.delivery.logger.warning")
    @patch("mailings.delivery.send_email")
    def test_retries_then_marks_message_as_sent(
        self,
        mocked_send_email,
        mocked_warning,
    ):
        mailing = self.create_mailing()
        mocked_send_email.side_effect = [RuntimeError("temporary"), None]

        stats = deliver_batch([mailing])

        mailing.refresh_from_db()
        self.assertEqual(mailing.delivery_status, MailingMessage.DeliveryStatus.SENT)
        self.assertEqual(mailing.delivery_attempts, 2)
        self.assertEqual(mailing.last_delivery_error, "")
        self.assertIsNotNone(mailing.sent_at)
        self.assertEqual(stats.messages, 1)
        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.failed, 0)
        self.assertEqual(stats.attempts, 2)
        self.assertEqual(stats.retries, 1)
        mocked_warning.assert_called_once_with(
            "Email delivery attempt failed: external_id=%s error=%s",
            "mailing-001",
            "RuntimeError",
        )

    @patch("mailings.delivery.logger.warning")
    @patch("mailings.delivery.send_email", side_effect=RuntimeError("unavailable"))
    def test_marks_message_as_failed_after_attempt_limit(
        self,
        mocked_send_email,
        mocked_warning,
    ):
        mailing = self.create_mailing()

        stats = deliver_batch([mailing])

        mailing.refresh_from_db()
        self.assertEqual(
            mocked_send_email.call_count,
            MAX_DELIVERY_ATTEMPTS,
        )
        self.assertEqual(
            mailing.delivery_status,
            MailingMessage.DeliveryStatus.FAILED,
        )
        self.assertEqual(mailing.delivery_attempts, MAX_DELIVERY_ATTEMPTS)
        self.assertEqual(mailing.last_delivery_error, "RuntimeError")
        self.assertIsNone(mailing.sent_at)
        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.failed, 1)
        self.assertEqual(stats.attempts, MAX_DELIVERY_ATTEMPTS)
        self.assertEqual(stats.retries, MAX_DELIVERY_ATTEMPTS - 1)
        self.assertEqual(mocked_warning.call_count, MAX_DELIVERY_ATTEMPTS)
        self.assertNotIn("unavailable", repr(mocked_warning.call_args_list))

    @patch("mailings.delivery.send_email")
    def test_delivers_multiple_messages_concurrently(self, mocked_send_email):
        barrier = Barrier(2)
        synchronization_errors = []

        def wait_for_other_worker(mailing):
            try:
                barrier.wait(timeout=2)
            except BrokenBarrierError as exc:
                synchronization_errors.append(exc)

        mocked_send_email.side_effect = wait_for_other_worker
        mailings = [
            self.create_mailing("mailing-001"),
            self.create_mailing("mailing-002"),
        ]

        stats = deliver_batch(mailings)

        self.assertEqual(synchronization_errors, [])
        self.assertEqual(stats.sent, 2)
        self.assertEqual(stats.attempts, 2)
