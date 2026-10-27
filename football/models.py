from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

class Source(models.TextChoices):
    DEMO = 'demo', 'Demonstration data'
    MANUAL = 'manual', 'Manually managed'
    API_FOOTBALL = 'api_football', 'API-Football'

class Competition(models.Model):
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=80)
    logo = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_competition_provider_id')]
    def __str__(self): return self.name

class Team(models.Model):
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=12)
    logo = models.URLField(blank=True)
    country = models.CharField(max_length=80)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_team_provider_id')]
    def __str__(self): return self.name

class Season(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='seasons')
    year = models.PositiveSmallIntegerField()
    current = models.BooleanField(default=False)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    provider_id = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['-year']
        constraints = [models.UniqueConstraint(fields=['competition','year'], name='unique_competition_season')]
    def __str__(self): return f'{self.competition} {self.year}'

class Player(models.Model):
    name = models.CharField(max_length=140)
    photo = models.URLField(blank=True)
    position = models.CharField(max_length=40, blank=True)
    nationality = models.CharField(max_length=80, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    shirt_number = models.PositiveSmallIntegerField(null=True, blank=True)
    height = models.CharField(max_length=20, blank=True)
    weight = models.CharField(max_length=20, blank=True)
    current_team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL, related_name='players')
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=64, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_player_provider_id')]
        indexes = [models.Index(fields=['source','position','name'])]
    def __str__(self): return self.name

class PlayerSeasonStats(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='season_stats')
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL)
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name='player_stats')
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='player_stats')
    payload = models.JSONField(default=dict)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.API_FOOTBALL)
    synced_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['player','team','competition','season'], name='unique_player_season_stats')]

class ProviderSyncStatus(models.Model):
    provider = models.CharField(max_length=32)
    resource = models.CharField(max_length=64)
    last_attempt = models.DateTimeField(auto_now=True)
    last_success = models.DateTimeField(null=True, blank=True)
    records_synced = models.PositiveIntegerField(default=0)
    error_message = models.CharField(max_length=300, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['provider','resource'], name='unique_provider_resource_status')]
    def __str__(self): return f'{self.provider}: {self.resource}'

class Match(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        LIVE = 'live', 'Live'
        COMPLETED = 'completed', 'Completed'
        POSTPONED = 'postponed', 'Postponed'
        CANCELLED = 'cancelled', 'Cancelled'
    competition = models.ForeignKey(Competition, on_delete=models.PROTECT, related_name='matches')
    home_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='away_matches')
    kickoff = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    season = models.ForeignKey(Season, null=True, blank=True, on_delete=models.SET_NULL, related_name='matches')
    venue = models.CharField(max_length=160, blank=True)
    round_name = models.CharField(max_length=100, blank=True)
    elapsed = models.PositiveSmallIntegerField(null=True, blank=True)
    provider_status = models.CharField(max_length=24, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL, db_index=True)
    provider_id = models.CharField(max_length=64, blank=True)
    provider_data = models.JSONField(default=dict, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['kickoff']
        indexes = [models.Index(fields=['status', 'kickoff']), models.Index(fields=['source','kickoff'])]
        constraints = [models.CheckConstraint(condition=~Q(home_team=F('away_team')), name='match_teams_must_differ'), models.UniqueConstraint(fields=['source','provider_id'], condition=~Q(provider_id=''), name='unique_match_provider_id')]
    def clean(self):
        if self.home_team_id and self.home_team_id == self.away_team_id:
            raise ValidationError('A team cannot play itself.')
        if (self.home_score is None) != (self.away_score is None):
            raise ValidationError('Both scores must be supplied together.')
    def __str__(self): return f'{self.home_team} v {self.away_team}'

class MatchEvent(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='events')
    provider_id = models.CharField(max_length=64, blank=True)
    elapsed = models.PositiveSmallIntegerField(null=True, blank=True)
    extra_time = models.PositiveSmallIntegerField(null=True, blank=True)
    event_type = models.CharField(max_length=60, blank=True)
    detail = models.CharField(max_length=160, blank=True)
    comments = models.CharField(max_length=200, blank=True)
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL)
    player = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='match_events')
    assist = models.ForeignKey(Player, null=True, blank=True, on_delete=models.SET_NULL, related_name='assists')
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.API_FOOTBALL)
    class Meta:
        ordering = ['elapsed','extra_time']
        constraints = [models.UniqueConstraint(fields=['match','provider_id'], condition=~Q(provider_id=''), name='unique_match_event_provider_id')]

class MatchLineup(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='lineups')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    formation = models.CharField(max_length=20, blank=True)
    coach = models.CharField(max_length=120, blank=True)
    starting_eleven = models.JSONField(default=list)
    substitutes = models.JSONField(default=list)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.API_FOOTBALL)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['match','team'], name='unique_team_lineup_per_match')]

class MatchStatistics(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='team_statistics')
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.API_FOOTBALL)
    synced_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['match','team'], name='unique_team_match_stats')]

class MatchPlayerStatistics(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='player_statistics')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='match_statistics')
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.API_FOOTBALL)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['match','player'], name='unique_player_match_stats')]

class SeasonStanding(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='standings')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='season_standings')
    rank = models.PositiveSmallIntegerField(null=True, blank=True)
    points = models.SmallIntegerField(null=True, blank=True)
    goals_for = models.PositiveSmallIntegerField(null=True, blank=True)
    goals_against = models.PositiveSmallIntegerField(null=True, blank=True)
    form = models.CharField(max_length=20, blank=True)
    payload = models.JSONField(default=dict)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.API_FOOTBALL)
    synced_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['rank']
        constraints = [models.UniqueConstraint(fields=['season','team'], name='unique_season_team_standing')]
