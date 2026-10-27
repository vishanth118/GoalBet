from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class Source(models.TextChoices):
    DEMO = 'demo', 'Demonstration data'
    MANUAL = 'manual', 'Manually managed'
    OPENF1 = 'openf1', 'OpenF1'

class Constructor(models.Model):
    name = models.CharField(max_length=100)
    nationality = models.CharField(max_length=80)
    color = models.CharField(max_length=7, default='#d92d35')
    logo = models.URLField(blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=80, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_constructor_provider_id')]
    def __str__(self): return self.name

class Driver(models.Model):
    name = models.CharField(max_length=120)
    abbreviation = models.CharField(max_length=3)
    number = models.PositiveSmallIntegerField()
    nationality = models.CharField(max_length=80)
    constructor = models.ForeignKey(Constructor, on_delete=models.PROTECT, related_name='drivers')
    image = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=100, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['number']
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_driver_provider_id')]
    def __str__(self): return f'{self.number} {self.abbreviation} | {self.name} ({self.constructor.name})'

class Circuit(models.Model):
    name = models.CharField(max_length=140)
    locality = models.CharField(max_length=100)
    country = models.CharField(max_length=80)
    time_zone = models.CharField(max_length=64, default='UTC', help_text='IANA time zone, for example Europe/Paris.')
    image = models.URLField(blank=True)
    length_km = models.DecimalField(max_digits=5, decimal_places=3, null=True, blank=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=80, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_circuit_provider_id')]
    def __str__(self): return self.name

class GrandPrix(models.Model):
    name = models.CharField(max_length=140)
    season = models.PositiveSmallIntegerField()
    round_number = models.PositiveSmallIntegerField()
    circuit = models.ForeignKey(Circuit, on_delete=models.PROTECT, related_name='grand_prix')
    drivers = models.ManyToManyField(Driver, blank=True, related_name='grand_prix_entries')
    demo = models.BooleanField(default=False)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=80, blank=True)
    date_start = models.DateTimeField(null=True, blank=True)
    date_end = models.DateTimeField(null=True, blank=True)
    gmt_offset = models.CharField(max_length=12, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['season', 'round_number']
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_grand_prix_provider_id')]
    def __str__(self): return f'{self.name} ({self.season})'

class Session(models.Model):
    class Type(models.TextChoices):
        PRACTICE = 'practice', 'Practice'
        QUALIFYING = 'qualifying', 'Qualifying'
        SPRINT = 'sprint', 'Sprint'
        SPRINT_QUALIFYING = 'sprint_qualifying', 'Sprint qualifying'
        GRAND_PRIX = 'grand_prix', 'Grand Prix'
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        LIVE = 'live', 'Live'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        UNAVAILABLE = 'unavailable', 'Status unavailable without live access'
    grand_prix = models.ForeignKey(GrandPrix, on_delete=models.CASCADE, related_name='sessions')
    session_type = models.CharField(max_length=24, choices=Type.choices)
    sequence = models.PositiveSmallIntegerField(default=1, help_text='Use 1, 2, or 3 to distinguish practice sessions.')
    start_time = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=80, blank=True)
    provider_data = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['start_time']
        constraints = [models.UniqueConstraint(fields=['grand_prix', 'session_type', 'sequence'], name='unique_session_per_gp_type_sequence'), models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_f1_session_provider_id')]
        indexes = [models.Index(fields=['status', 'start_time'])]
    def __str__(self): return f'{self.grand_prix} · {self.get_session_type_display()}'

class F1ChampionshipStanding(models.Model):
    class Kind(models.TextChoices):
        DRIVER = 'driver', 'Driver'
        CONSTRUCTOR = 'constructor', 'Constructor'
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='championship_standings')
    kind = models.CharField(max_length=12, choices=Kind.choices)
    provider_id = models.CharField(max_length=100)
    entity_name = models.CharField(max_length=120)
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    points_start = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    points_current = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL)
    constructor = models.ForeignKey(Constructor, null=True, blank=True, on_delete=models.SET_NULL)
    synced_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['kind','position']
        constraints = [models.UniqueConstraint(fields=['session','kind','provider_id'], name='unique_f1_standing_per_session')]

class LapRecord(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='laps')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='laps')
    lap_number = models.PositiveSmallIntegerField()
    duration_seconds = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    is_pit_out = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['session','driver','lap_number'], name='unique_f1_lap')]
        indexes = [models.Index(fields=['session','driver','lap_number'])]

class PitStop(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='pit_stops')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='pit_stops')
    lap_number = models.PositiveSmallIntegerField(null=True, blank=True)
    stop_duration = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['session','driver','lap_number'], name='unique_f1_pit_stop')]

class RaceControlEvent(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='race_control_events')
    provider_id = models.CharField(max_length=100)
    occurred_at = models.DateTimeField(null=True, blank=True)
    category = models.CharField(max_length=40, blank=True)
    flag = models.CharField(max_length=40, blank=True)
    message = models.CharField(max_length=400, blank=True)
    driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['session','provider_id'], name='unique_f1_control_event')]

class WeatherObservation(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='weather_observations')
    observed_at = models.DateTimeField()
    air_temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    track_temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rainfall = models.BooleanField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['session','observed_at'], name='unique_f1_weather_sample')]

class RaceResult(models.Model):
    class Status(models.TextChoices):
        FINISHED = 'finished', 'Finished'
        RETIRED = 'retired', 'Retired'
        DID_NOT_START = 'dns', 'Did not start'
        DISQUALIFIED = 'disqualified', 'Disqualified'
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='results')
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name='results')
    constructor = models.ForeignKey(Constructor, on_delete=models.PROTECT, related_name='results')
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    points = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=None)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.FINISHED)
    fastest_lap = models.BooleanField(default=False)
    fastest_lap_known = models.BooleanField(default=False)
    provider_data = models.JSONField(default=dict, blank=True)
    class Meta:
        ordering = ['position', 'driver__number']
        constraints = [
            models.UniqueConstraint(fields=['session', 'driver'], name='unique_driver_result_per_session'),
            models.UniqueConstraint(fields=['session', 'position'], condition=models.Q(position__isnull=False), name='unique_f1_position_per_session'),
        ]
    def clean(self):
        if self.driver_id and self.constructor_id and self.driver.constructor_id != self.constructor_id:
            raise ValidationError({'constructor': 'Choose the driver’s registered constructor.'})
        if self.fastest_lap and self.status != self.Status.FINISHED:
            raise ValidationError({'fastest_lap': 'Only a finishing driver may receive fastest lap.'})
    def __str__(self): return f'{self.session} · {self.driver} · {self.position or self.get_status_display()}'
