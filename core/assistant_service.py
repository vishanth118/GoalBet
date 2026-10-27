"""Database-grounded help answers and optional server-side AI narration."""
import logging
import hashlib
import re
import uuid

from django.conf import settings
from django.db import DatabaseError
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from .models import ErrorCode, FAQ, SupportTicket

logger = logging.getLogger('goalbet')
ERROR_PATTERN = re.compile(r'\b(?:HTTP\s*)?(400|401|403|404|429|500|503|GB-001)\b', re.I)
EMAIL_PATTERN = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')
SECRET_PATTERN = re.compile(r'(?i)\b(password|passwd|api[_ -]?key|token|authorization)\s*[:=]\s*[^\s,;]+')


def _mongo_collection(name):
    if not settings.MONGODB_URI:
        return None
    try:
        from pymongo import MongoClient
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1200, connectTimeoutMS=1200)
        client.admin.command('ping')
        return client[settings.MONGODB_DATABASE][name]
    except Exception as exc:
        logger.warning('MongoDB %s unavailable (%s)', name, type(exc).__name__)
        return None


def write_chat_log(document):
    collection = _mongo_collection('conversations')
    if collection is None:
        return False
    try:
        collection.insert_one(document)
        return True
    except Exception as exc:
        logger.warning('MongoDB conversation write failed (%s)', type(exc).__name__)
        return False


def save_feedback(conversation_id, helpful, comment=''):
    collection = _mongo_collection('feedback')
    if collection is None:
        return False
    try:
        collection.insert_one({'conversation_id': conversation_id, 'helpful': helpful, 'comment': _redact_for_log(comment)[:500], 'timestamp': timezone.now()})
        return True
    except Exception as exc:
        logger.warning('MongoDB feedback write failed (%s)', type(exc).__name__)
        return False


def _redact_for_log(text):
    text = SECRET_PATTERN.sub(r'\1=[redacted]', text)
    return EMAIL_PATTERN.sub('[email redacted]', text)[:5000]


def _fallback_answer(message, faqs, error):
    if error:
        return f"{error.title} ({error.code}): {error.explanation} Try this: {error.troubleshooting}"
    if faqs:
        return 'Here is the closest information in GoalBet help: ' + faqs[0].answer
    return "Could you clarify which GoalBet page or feature you mean? I couldn't find a reliable answer in the help information, so I have sent this question to support for follow-up."


def _ai_answer(message, context):
    if not settings.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=12.0, max_retries=0)
        response = client.responses.create(
            model=settings.OPENAI_MODEL,
            instructions=("Answer support questions briefly using only the supplied GoalBet FAQ/error context. "
                          "If context does not answer the question, say so and invite a support ticket. "
                          "Never claim an action was completed unless the application confirms it."),
            input=f"GoalBet help context:\n{context}\n\nVisitor question:\n{message}",
            max_output_tokens=300,
        )
        return response.output_text.strip() or None
    except Exception as exc:
        logger.warning('Assistant provider unavailable (%s)', type(exc).__name__)
        return None


def answer_question(message, user=None, request=None, create_ticket=False):
    conversation_id = uuid.uuid4().hex
    error_match = ERROR_PATTERN.search(message)
    error = ErrorCode.objects.filter(active=True, code__iexact=error_match.group(1)).first() if error_match else None
    words = [word for word in re.findall(r'[a-zA-Z0-9]{3,}', message.lower()) if word not in {'what', 'does', 'how', 'can', 'the', 'and', 'for', 'with', 'this', 'that', 'help', 'please'}]
    faqs = FAQ.objects.filter(active=True)
    if words:
        query = Q()
        relevance = Value(0, output_field=IntegerField())
        for word in words[:8]:
            question_match = Q(question__icontains=word)
            answer_match = Q(answer__icontains=word)
            query |= question_match | answer_match
            relevance += Case(
                When(question_match, then=Value(3)),
                When(answer_match, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        faqs = faqs.filter(query).annotate(relevance=relevance).order_by('-relevance', 'question')[:3]
    else:
        faqs = faqs.none()
    context = '\n'.join([f"FAQ: {item.question}\nAnswer: {item.answer}" for item in faqs])
    if error:
        context += f"\nError {error.code}: {error.title}. {error.explanation} Causes: {error.common_causes}. Steps: {error.troubleshooting}"
    faq_items = list(faqs)
    has_confident_faq_match = bool(faq_items and faq_items[0].relevance >= 5)
    fallback = _fallback_answer(message, faq_items if has_confident_faq_match else [], error)
    is_resolved = bool(error or has_confident_faq_match)
    response = _ai_answer(message, context) if is_resolved else None
    mode = 'openai' if response else 'database_fallback'
    response = response or fallback
    ticket = None
    explicit = bool(re.search(r'\b(ticket|support agent|human support|contact support)\b', message, re.I))
    if create_ticket or explicit or not is_resolved:
        try:
            ticket = SupportTicket.objects.create(
                subject=message[:160] or 'GoalBet support request', question=message[:5000],
                user=user if getattr(user, 'is_authenticated', False) else None,
                conversation_id=conversation_id,
            )
            response += f' Support ticket {ticket.reference} was created successfully.'
        except DatabaseError:
            logger.exception('Support ticket could not be saved')
            response += ' I could not save a support ticket right now. Please try again or use the support form.'
    if request is not None:
        write_chat_log({
            'conversation_id': conversation_id, 'timestamp': timezone.now(),
            'user_message': _redact_for_log(message), 'assistant_response': _redact_for_log(response),
            'faq_ids': [item.pk for item in faq_items], 'error_code': error.code if error else None,
            'ticket_created': bool(ticket), 'provider_mode': mode,
            'user_reference': hashlib.sha256(f'{settings.SECRET_KEY}:{user.pk}'.encode()).hexdigest()[:24] if getattr(user, 'is_authenticated', False) else None,
        })
    return {'conversation_id': conversation_id, 'answer': response, 'ticket_reference': ticket.reference if ticket else None, 'mode': mode, 'resolved': is_resolved}
