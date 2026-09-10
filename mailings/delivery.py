import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from random import randint
from time import sleep

from django.utils import timezone

from mailings.models import MailingMessage

MIN_SEND_DELAY_SECONDS = 5
MAX_SEND_DELAY_SECONDS = 20
MAX_DELIVERY_ATTEMPTS = 3
MAX_DELIVERY_WORKERS = 4
DELIVERY_BATCH_SIZE = 100

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeliveryStats:
    messages: int = 0
    sent: int = 0
    failed: int = 0
    attempts: int = 0

    @property
    def retries(self) -> int:
        return self.attempts - self.messages

    def __add__(self, other: "DeliveryStats") -> "DeliveryStats":
        return DeliveryStats(
            messages=self.messages + other.messages,
            sent=self.sent + other.sent,
            failed=self.failed + other.failed,
            attempts=self.attempts + other.attempts,
        )


@dataclass(frozen=True, slots=True)
class _DeliveryResult:
    sent: bool
    attempts: int
    error_type: str = ""


def send_email(mailing: MailingMessage) -> None:
    """Simulate sending an email after the required delay."""
    delay = randint(MIN_SEND_DELAY_SECONDS, MAX_SEND_DELAY_SECONDS)
    sleep(delay)
    logger.info("Email sent: external_id=%s", mailing.external_id)


def deliver_batch(mailings: Sequence[MailingMessage]) -> DeliveryStats:
    """Deliver a bounded batch concurrently and persist results serially."""
    if not mailings:
        return DeliveryStats()

    worker_count = min(MAX_DELIVERY_WORKERS, len(mailings))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(_deliver_with_retries, mailings))

    completed_at = timezone.now()
    sent = 0
    attempts = 0
    for mailing, result in zip(mailings, results, strict=True):
        attempts += result.attempts
        mailing.delivery_attempts += result.attempts
        if result.sent:
            sent += 1
            mailing.delivery_status = MailingMessage.DeliveryStatus.SENT
            mailing.last_delivery_error = ""
            mailing.sent_at = completed_at
        else:
            mailing.delivery_status = MailingMessage.DeliveryStatus.FAILED
            mailing.last_delivery_error = result.error_type
            mailing.sent_at = None

    MailingMessage.objects.bulk_update(
        mailings,
        (
            "delivery_status",
            "delivery_attempts",
            "last_delivery_error",
            "sent_at",
        ),
    )
    return DeliveryStats(
        messages=len(mailings),
        sent=sent,
        failed=len(mailings) - sent,
        attempts=attempts,
    )


def _deliver_with_retries(mailing: MailingMessage) -> _DeliveryResult:
    last_error_type = ""
    for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
        try:
            send_email(mailing)
        except Exception as exc:  # noqa: BLE001 - delivery is the retry boundary
            last_error_type = type(exc).__name__
            logger.warning(
                "Email delivery attempt failed: external_id=%s error=%s",
                mailing.external_id,
                last_error_type,
            )
        else:
            return _DeliveryResult(sent=True, attempts=attempt)

    return _DeliveryResult(
        sent=False,
        attempts=MAX_DELIVERY_ATTEMPTS,
        error_type=last_error_type,
    )
