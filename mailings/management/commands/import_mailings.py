from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from mailings.delivery import send_email
from mailings.models import MailingMessage
from mailings.xlsx import XlsxFormatError, build_mailing_message, iter_xlsx_rows


class Command(BaseCommand):
    help = "Import mailing messages from an XLSX file."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "xlsx_file",
            type=Path,
            help="Path to the XLSX file to import.",
        )

    def handle(self, *args, **options) -> None:
        processed = 0
        created = 0
        skipped = 0
        errors = 0

        try:
            rows = iter_xlsx_rows(options["xlsx_file"])
            for row_number, row_data in rows:
                processed += 1

                try:
                    mailing = build_mailing_message(row_data)
                except ValidationError as exc:
                    errors += 1
                    self.stderr.write(
                        f"Row {row_number}: {_format_validation_error(exc)}"
                    )
                    continue

                stored_mailing, was_created = MailingMessage.objects.get_or_create(
                    external_id=mailing.external_id,
                    defaults={
                        "user_id": mailing.user_id,
                        "email": mailing.email,
                        "subject": mailing.subject,
                        "message": mailing.message,
                    },
                )
                if was_created:
                    created += 1
                    send_email(stored_mailing)
                else:
                    skipped += 1
        except XlsxFormatError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            "Import completed: "
            f"processed={processed}, "
            f"created={created}, "
            f"skipped={skipped}, "
            f"errors={errors}"
        )


def _format_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {', '.join(str(message) for message in messages)}"
            for field, messages in sorted(error.message_dict.items())
        )
    return "; ".join(str(message) for message in error.messages)
