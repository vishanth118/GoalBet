from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1000.00'), validators=[MinValueValidator(Decimal('0'))])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return f'{self.user} — {self.balance} VC'

class Prediction(models.Model):
    class Market(models.TextChoices):
        MATCH_RESULT = 'match_result', 'Match result'
        BOTH_TEAMS_SCORE = 'both_score', 'Both teams to score'
        TOTAL_GOALS = 'total_goals', 'Total goals'
    class Outcome(models.TextChoices):
        HOME = 'home', 'Home win'
        DRAW = 'draw', 'Draw'
        AWAY = 'away', 'Away win'
        YES = 'yes', 'Yes'
        NO = 'no', 'No'
        OVER_25 = 'over_2_5', 'Over 2.5 goals'
        UNDER_25 = 'under_2_5', 'Under 2.5 goals'
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'
        VOID = 'void', 'Void'
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='predictions')
    match = models.ForeignKey('football.Match', on_delete=models.PROTECT, related_name='predictions')
    market = models.CharField(max_length=16, choices=Market.choices, default=Market.MATCH_RESULT)
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    stake = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    multiplier = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    profit_loss = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'match', 'market'], name='unique_prediction_per_user_match_market')]
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status'])]
    def __str__(self): return f'{self.user}: {self.match} ({self.outcome})'

class Transaction(models.Model):
    class Type(models.TextChoices):
        GRANT = 'grant', 'Welcome credits'
        STAKE = 'stake', 'Prediction stake'
        WIN = 'win', 'Prediction win'
        REFUND = 'refund', 'Prediction refund'
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=8, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f'{self.get_type_display()}: {self.amount}'

class F1Prediction(models.Model):
    class Market(models.TextChoices):
        RACE_WINNER = 'race_winner', 'Race winner'
        PODIUM = 'podium', 'Podium finish'
        POLE = 'pole', 'Pole position'
        FASTEST_LAP = 'fastest_lap', 'Fastest lap'
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'
        VOID = 'void', 'Void'
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='f1_predictions')
    session = models.ForeignKey('formula1.Session', on_delete=models.PROTECT, related_name='predictions')
    market = models.CharField(max_length=16, choices=Market.choices)
    selected_driver = models.ForeignKey('formula1.Driver', on_delete=models.PROTECT, related_name='predictions')
    stake = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    multiplier = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    profit_loss = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['user', 'session', 'market'], name='unique_f1_prediction_market_per_user')]
    def __str__(self): return f'{self.user} · {self.session} · {self.get_market_display()}'
