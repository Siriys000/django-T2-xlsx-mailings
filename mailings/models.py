from django.db import models


class MailingMessage(models.Model):
    """An email message imported from one XLSX row."""

    external_id = models.CharField(max_length=255, unique=True)
    user_id = models.PositiveBigIntegerField()
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()

    def __str__(self) -> str:
        return self.external_id
