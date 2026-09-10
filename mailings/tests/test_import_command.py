from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase
from openpyxl import Workbook

from mailings.models import MailingMessage


HEADERS = ["external_id", "user_id", "email", "subject", "message"]


class ImportMailingsCommandTests(TestCase):
    def setUp(self):
        self.temp_directory = TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        send_email_patcher = patch(
            "mailings.management.commands.import_mailings.send_email"
        )
        self.mocked_send_email = send_email_patcher.start()
        self.addCleanup(send_email_patcher.stop)

    def write_workbook(self, rows):
        path = Path(self.temp_directory.name) / "mailings.xlsx"
        workbook = Workbook()
        worksheet = workbook.active
        for row in rows:
            worksheet.append(row)
        workbook.save(path)
        workbook.close()
        return path

    def run_command(self, path):
        stdout = StringIO()
        stderr = StringIO()
        call_command("import_mailings", path, stdout=stdout, stderr=stderr)
        return stdout.getvalue(), stderr.getvalue()

    def test_imports_valid_rows_and_reports_summary(self):
        path = self.write_workbook(
            [
                HEADERS,
                ["mailing-001", 1, "one@example.com", "First", "Message one"],
                ["mailing-002", 2, "two@example.com", "Second", "Message two"],
            ]
        )

        stdout, stderr = self.run_command(path)

        self.assertEqual(MailingMessage.objects.count(), 2)
        sent_messages = [
            call.args[0] for call in self.mocked_send_email.call_args_list
        ]
        self.assertEqual(
            [mailing.external_id for mailing in sent_messages],
            ["mailing-001", "mailing-002"],
        )
        self.assertTrue(all(mailing.pk for mailing in sent_messages))
        self.assertEqual(stderr, "")
        self.assertIn(
            "Import completed: processed=2, created=2, skipped=0, errors=0",
            stdout,
        )

    def test_reimport_skips_existing_message_without_overwriting_it(self):
        existing = MailingMessage.objects.create(
            external_id="mailing-001",
            user_id=1,
            email="original@example.com",
            subject="Original",
            message="Original message",
        )
        path = self.write_workbook(
            [
                HEADERS,
                [
                    "mailing-001",
                    99,
                    "changed@example.com",
                    "Changed",
                    "Changed message",
                ],
            ]
        )

        stdout, _ = self.run_command(path)

        existing.refresh_from_db()
        self.assertEqual(existing.user_id, 1)
        self.assertEqual(existing.email, "original@example.com")
        self.assertEqual(existing.subject, "Original")
        self.assertEqual(existing.message, "Original message")
        self.mocked_send_email.assert_not_called()
        self.assertIn("processed=1, created=0, skipped=1, errors=0", stdout)

    def test_duplicate_inside_file_is_created_once(self):
        path = self.write_workbook(
            [
                HEADERS,
                ["mailing-001", 1, "one@example.com", "First", "Message one"],
                ["mailing-001", 2, "two@example.com", "Second", "Message two"],
            ]
        )

        stdout, _ = self.run_command(path)

        mailing = MailingMessage.objects.get()
        self.assertEqual(mailing.email, "one@example.com")
        self.mocked_send_email.assert_called_once_with(mailing)
        self.assertIn("processed=2, created=1, skipped=1, errors=0", stdout)

    def test_invalid_row_does_not_stop_import_or_expose_message(self):
        path = self.write_workbook(
            [
                HEADERS,
                [
                    "mailing-001",
                    1,
                    "invalid-email",
                    "Invalid",
                    "private message body",
                ],
                ["mailing-002", 2, "two@example.com", "Valid", "Message two"],
            ]
        )

        stdout, stderr = self.run_command(path)

        mailing = MailingMessage.objects.get()
        self.assertEqual(mailing.external_id, "mailing-002")
        self.mocked_send_email.assert_called_once_with(mailing)
        self.assertIn("processed=2, created=1, skipped=0, errors=1", stdout)
        self.assertIn("Row 2", stderr)
        self.assertIn("email", stderr)
        self.assertNotIn("private message body", stderr)

    def test_invalid_headers_abort_without_creating_messages(self):
        path = self.write_workbook(
            [
                ["external_id", "user_id", "email", "subject"],
                ["mailing-001", 1, "one@example.com", "First"],
            ]
        )

        with self.assertRaisesRegex(CommandError, "message"):
            self.run_command(path)

        self.assertFalse(MailingMessage.objects.exists())
        self.mocked_send_email.assert_not_called()

    def test_corrupted_workbook_raises_command_error(self):
        path = Path(self.temp_directory.name) / "mailings.xlsx"
        path.write_text("not a workbook", encoding="utf-8")

        with self.assertRaises(CommandError):
            self.run_command(path)

        self.assertFalse(MailingMessage.objects.exists())
        self.mocked_send_email.assert_not_called()
