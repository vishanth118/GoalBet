import secrets
import string

from django.conf import settings
from django.db import models


class FAQ(models.Model):
    question = models.CharField(max_length=240)
    answer = models.TextField()
    category = models.CharField(max_length=60, default='General')
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'question']
        verbose_name = 'Frequently asked question'

    def __str__(self):
        return self.question


class ErrorCode(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=120)
    explanation = models.TextField()
    common_causes = models.TextField(blank=True)
    troubleshooting = models.TextField()
    active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code}: {self.title}'


def ticket_reference():
    alphabet = string.ascii_uppercase + string.digits
    return 'GB-' + ''.join(secrets.choice(alphabet) for _ in range(10))


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In progress'
        RESOLVED = 'resolved', 'Resolved'

    reference = models.CharField(max_length=13, unique=True, default=ticket_reference, editable=False)
    subject = models.CharField(max_length=160)
    question = models.TextField()
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='support_tickets')
    conversation_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference}: {self.subject}'
