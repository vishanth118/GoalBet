from django.contrib import admin
from .models import F1Prediction, Prediction, Transaction, Wallet

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'match', 'outcome', 'stake', 'status', 'profit_loss')
    list_filter = ('status', 'outcome')
    readonly_fields = ('user', 'match', 'outcome', 'stake', 'multiplier', 'status', 'profit_loss', 'created_at', 'settled_at')
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'updated_at')
    readonly_fields = ('user', 'balance', 'created_at', 'updated_at')
@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'type', 'amount', 'balance_after', 'created_at')
    readonly_fields = tuple(f.name for f in Transaction._meta.fields)

@admin.register(F1Prediction)
class F1PredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'session', 'market', 'selected_driver', 'stake', 'status', 'profit_loss')
    list_filter = ('status', 'market', 'session__session_type')
    readonly_fields = ('user', 'session', 'market', 'selected_driver', 'stake', 'multiplier', 'status', 'profit_loss', 'created_at', 'settled_at')
