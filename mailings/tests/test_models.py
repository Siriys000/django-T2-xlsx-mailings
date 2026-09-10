from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from mailings.models import MailingMessage


class MailingMessageModelTests(TestCase):
    @staticmethod
    def valid_data(**overrides):
        data = {
            "external_id": "mailing-001",
            "user_id": 42,
            "email": "recipient@example.com",
            "subject": "Important update",
            "message": "Message body",
        }
        data.update(overrides)
        return data

    def test_stores_xlsx_row_as_a_message(self):
        mailing = MailingMessage.objects.create(**self.valid_data())

        mailing.refresh_from_db()

        self.assertEqual(mailing.external_id, "mailing-001")
        self.assertEqual(mailing.user_id, 42)
        self.assertEqual(mailing.email, "recipient@example.com")
        self.assertEqual(mailing.subject, "Important update")
        self.assertEqual(mailing.message, "Message body")

    def test_external_id_is_unique(self):
        MailingMessage.objects.create(**self.valid_data())

        with self.assertRaises(IntegrityError), transaction.atomic():
            MailingMessage.objects.create(
                **self.valid_data(email="another@example.com")
            )

    def test_rejects_invalid_email_during_validation(self):
        mailing = MailingMessage(**self.valid_data(email="not-an-email"))

        with self.assertRaises(ValidationError) as raised:
            mailing.full_clean()

        self.assertIn("email", raised.exception.message_dict)

    def test_rejects_blank_required_fields_during_validation(self):
        mailing = MailingMessage(
            external_id="",
            user_id=42,
            email="",
            subject="",
            message="",
        )

        with self.assertRaises(ValidationError) as raised:
            mailing.full_clean()

        self.assertEqual(
            set(raised.exception.message_dict),
            {"external_id", "email", "subject", "message"},
        )

    def test_rejects_negative_user_id_during_validation(self):
        mailing = MailingMessage(**self.valid_data(user_id=-1))

        with self.assertRaises(ValidationError) as raised:
            mailing.full_clean()

        self.assertIn("user_id", raised.exception.message_dict)
