from django.contrib import admin
from .models import ErrorCode, FAQ, SupportTicket


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ('question', 'category', 'active', 'updated_at')
    list_filter = ('category', 'active')
    search_fields = ('question', 'answer')


@admin.register(ErrorCode)
class ErrorCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'active')
    list_filter = ('active',)
    search_fields = ('code', 'title', 'explanation')


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('reference', 'subject', 'status', 'user', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('reference', 'subject', 'question', 'user__username')
    readonly_fields = ('reference', 'question', 'description', 'user', 'conversation_id', 'created_at', 'updated_at')
