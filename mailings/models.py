from django.db import models


class MailingMessage(models.Model):
    """An email message imported from one XLSX row."""

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    external_id = models.CharField(max_length=255, unique=True)
    user_id = models.PositiveBigIntegerField()
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    delivery_status = models.CharField(
        max_length=16,
        choices=DeliveryStatus,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    delivery_attempts = models.PositiveIntegerField(default=0)
    last_delivery_error = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        delivery_status="sent",
                        sent_at__isnull=False,
                    )
                    | models.Q(
                        delivery_status__in=("pending", "failed"),
                        sent_at__isnull=True,
                    )
                ),
                name="mailing_sent_status_matches_timestamp",
            ),
        ]

    def __str__(self) -> str:
        return self.external_id
