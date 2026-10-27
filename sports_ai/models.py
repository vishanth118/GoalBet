from django.db import models

class SportsAnalysis(models.Model):
    class Sport(models.TextChoices):
        SOCCER = 'soccer', 'Soccer'
        F1 = 'f1', 'Formula 1'
    class Status(models.TextChoices):
        READY = 'ready', 'Statistical estimate available'
        INSUFFICIENT = 'insufficient', 'Insufficient provider history'
        UNAVAILABLE = 'unavailable', 'Analysis unavailable'
    sport = models.CharField(max_length=8, choices=Sport.choices)
    target_type = models.CharField(max_length=32)
    target_provider_id = models.CharField(max_length=100)
    model_version = models.CharField(max_length=40)
    status = models.CharField(max_length=16, choices=Status.choices)
    sample_size = models.PositiveIntegerField(default=0)
    input_data = models.JSONField(default=dict)
    estimates = models.JSONField(default=dict)
    data_as_of = models.DateTimeField(null=True, blank=True)
    explanation = models.TextField(blank=True)
    explanation_model = models.CharField(max_length=80, blank=True)
    explanation_status = models.CharField(max_length=24, blank=True)
    generated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-generated_at']
        constraints = [models.UniqueConstraint(fields=['sport','target_type','target_provider_id','model_version'], name='unique_analysis_target_version')]

class SportsModelEvaluation(models.Model):
    sport = models.CharField(max_length=8, choices=SportsAnalysis.Sport.choices)
    model_version = models.CharField(max_length=40)
    evaluated_at = models.DateTimeField(auto_now_add=True)
    sample_size = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(default=dict)
    notes = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=32)
