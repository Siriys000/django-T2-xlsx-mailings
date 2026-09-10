from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from mailings.delivery import DELIVERY_BATCH_SIZE, DeliveryStats, deliver_batch
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
        delivery_stats = DeliveryStats()
        pending_batch: list[MailingMessage] = []

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
                    pending_batch.append(stored_mailing)
                    if len(pending_batch) >= DELIVERY_BATCH_SIZE:
                        delivery_stats += deliver_batch(pending_batch)
                        pending_batch.clear()
                else:
                    skipped += 1
        except XlsxFormatError as exc:
            raise CommandError(str(exc)) from exc

        delivery_stats += deliver_batch(pending_batch)

        self.stdout.write(
            "Import completed: "
            f"processed={processed}, "
            f"created={created}, "
            f"skipped={skipped}, "
            f"errors={errors}, "
            f"sent={delivery_stats.sent}, "
            f"send_failed={delivery_stats.failed}, "
            f"attempts={delivery_stats.attempts}, "
            f"retries={delivery_stats.retries}"
        )


def _format_validation_error(error: ValidationError) -> str:
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {', '.join(str(message) for message in messages)}"
            for field, messages in sorted(error.message_dict.items())
        )
    return "; ".join(str(message) for message in error.messages)
