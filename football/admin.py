from django.contrib import admin
from .models import Competition, Team, Match

@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin): list_display = ('name', 'country', 'active'); search_fields = ('name', 'country')
@admin.register(Team)
class TeamAdmin(admin.ModelAdmin): list_display = ('name', 'short_name', 'country'); search_fields = ('name', 'short_name')
@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'competition', 'kickoff', 'status', 'home_score', 'away_score')
    list_filter = ('competition', 'status')
    actions = ['settle_completed_matches', 'void_matches']
    @admin.action(description='Settle completed matches with final scores')
    def settle_completed_matches(self, request, queryset):
        from predictions.services import settle_match
        count = sum(settle_match(m.pk) for m in queryset if m.status == Match.Status.COMPLETED and m.home_score is not None and m.away_score is not None)
        self.message_user(request, f'Settled {count} match(es).')
    @admin.action(description='Void and refund predictions for postponed/cancelled matches')
    def void_matches(self, request, queryset):
        from predictions.services import void_match
        count = sum(void_match(m.pk) for m in queryset if m.status in (Match.Status.POSTPONED, Match.Status.CANCELLED))
        self.message_user(request, f'Voided {count} prediction(s).')
