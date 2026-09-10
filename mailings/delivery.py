import logging
from random import randint
from time import sleep

from mailings.models import MailingMessage

MIN_SEND_DELAY_SECONDS = 5
MAX_SEND_DELAY_SECONDS = 20

logger = logging.getLogger(__name__)


def send_email(mailing: MailingMessage) -> None:
    """Simulate sending an email after the required delay."""
    delay = randint(MIN_SEND_DELAY_SECONDS, MAX_SEND_DELAY_SECONDS)
    sleep(delay)
    logger.info("Email sent: external_id=%s", mailing.external_id)
