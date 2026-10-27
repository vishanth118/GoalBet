from django.contrib import admin, messages
from .models import Circuit, Constructor, Driver, GrandPrix, RaceResult, Session

@admin.register(Constructor)
class ConstructorAdmin(admin.ModelAdmin):
    list_display = ('name', 'nationality')
    search_fields = ('name', 'nationality')

@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('number', 'abbreviation', 'name', 'constructor', 'active')
    list_filter = ('constructor', 'active', 'nationality')
    search_fields = ('name', 'abbreviation')

@admin.register(Circuit)
class CircuitAdmin(admin.ModelAdmin):
    list_display = ('name', 'locality', 'country', 'length_km')
    search_fields = ('name', 'locality', 'country')

@admin.register(GrandPrix)
class GrandPrixAdmin(admin.ModelAdmin):
    list_display = ('name', 'season', 'round_number', 'circuit', 'demo')
    list_filter = ('season', 'demo')

class RaceResultInline(admin.TabularInline):
    model = RaceResult
    extra = 0

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('grand_prix', 'session_type', 'start_time', 'status')
    list_filter = ('session_type', 'status', 'grand_prix__season')
    inlines = [RaceResultInline]
    actions = ('settle_predictions', 'void_predictions')

    @admin.action(description='Settle predictions from finalized session results')
    def settle_predictions(self, request, queryset):
        from .services.prediction_settlement import settle_f1_session
        settled = sum(settle_f1_session(session.pk) for session in queryset if session.status == Session.Status.COMPLETED)
        self.message_user(request, f'Settled {settled} prediction(s).', messages.SUCCESS)

    @admin.action(description='Void cancelled sessions and refund virtual credits')
    def void_predictions(self, request, queryset):
        from .services.prediction_settlement import void_f1_session
        voided = sum(void_f1_session(session.pk) for session in queryset if session.status == Session.Status.CANCELLED)
        self.message_user(request, f'Voided {voided} prediction(s).', messages.SUCCESS)

@admin.register(RaceResult)
class RaceResultAdmin(admin.ModelAdmin):
    list_display = ('session', 'position', 'driver', 'constructor', 'points', 'status', 'fastest_lap')
    list_filter = ('session__grand_prix__season', 'session__session_type', 'status', 'fastest_lap')
    search_fields = ('driver__name', 'constructor__name', 'session__grand_prix__name')
