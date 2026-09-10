from django.core.management.base import BaseCommand

from mailings.delivery import DELIVERY_BATCH_SIZE, DeliveryStats, deliver_batch
from mailings.models import MailingMessage


class Command(BaseCommand):
    help = "Retry pending and failed mailing deliveries."

    def handle(self, *args, **options) -> None:
        delivery_stats = DeliveryStats()
        last_pk = 0

        while True:
            batch = list(
                MailingMessage.objects.filter(
                    pk__gt=last_pk,
                    delivery_status__in=(
                        MailingMessage.DeliveryStatus.PENDING,
                        MailingMessage.DeliveryStatus.FAILED,
                    ),
                ).order_by("pk")[:DELIVERY_BATCH_SIZE]
            )
            if not batch:
                break

            last_pk = batch[-1].pk
            delivery_stats += deliver_batch(batch)

        self.stdout.write(
            "Retry completed: "
            f"processed={delivery_stats.messages}, "
            f"sent={delivery_stats.sent}, "
            f"failed={delivery_stats.failed}, "
            f"attempts={delivery_stats.attempts}, "
            f"retries={delivery_stats.retries}"
        )
