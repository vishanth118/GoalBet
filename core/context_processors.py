from django.conf import settings


def assistant_config(request):
    return {'assistant_enabled': True, 'assistant_ai_configured': bool(settings.OPENAI_API_KEY)}
