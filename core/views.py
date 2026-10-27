from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, F, FloatField, ExpressionWrapper
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.db import connections, DatabaseError
from django.db.utils import OperationalError
import hashlib
import json
import logging
import re
from .models import FAQ, ErrorCode, SupportTicket
from .assistant_service import answer_question, save_feedback
from .forms import SupportTicketForm
from football.models import Competition, Match
from predictions.forms import PredictionForm, RegistrationForm
from predictions.models import F1Prediction, Prediction
from predictions.services import place_prediction

User = get_user_model()
logger = logging.getLogger('goalbet')

def _rate_limited(request, prefix, limit, period=60):
    identity = request.META.get('REMOTE_ADDR', 'unknown')
    key = f'{prefix}:{hashlib.sha256(identity.encode()).hexdigest()}'
    if cache.add(key, 1, timeout=period):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, timeout=period)
        return False

def faq_page(request):
    return render(request, 'core/faq.html', {'faqs': FAQ.objects.filter(active=True)})

def error_codes_page(request):
    errors = ErrorCode.objects.filter(active=True)
    term = request.GET.get('q', '').strip()[:80]
    if term:
        errors = errors.filter(Q(code__icontains=term) | Q(title__icontains=term) | Q(explanation__icontains=term))
    return render(request, 'core/error_codes.html', {'errors': errors, 'query': term})

def support_page(request):
    return render(request, 'core/support.html', {'form': SupportTicketForm(require_email=not request.user.is_authenticated)})

@require_POST
def submit_ticket(request):
    from django.conf import settings
    form = SupportTicketForm(request.POST, require_email=not request.user.is_authenticated)
    if _rate_limited(request, 'ticket', settings.TICKET_RATE_LIMIT):
        return render(request, 'core/support.html', {'error': 'Please wait a minute before sending another request.', 'form': form}, status=429)
    if not form.is_valid():
        return render(request, 'core/support.html', {'error': 'Please correct the fields below.', 'form': form}, status=400)
    subject = form.cleaned_data['subject']
    question = form.cleaned_data['question']
    description = form.cleaned_data['description']
    email = form.cleaned_data['email']
    try:
        ticket = SupportTicket.objects.create(subject=subject, question=question, description=(f'Contact email: {email}\n' if email and not request.user.is_authenticated else '') + description, user=request.user if request.user.is_authenticated else None)
    except DatabaseError:
        logger.exception('Support ticket form submission failed')
        return render(request, 'core/support.html', {'error': 'We could not save your request. Please try again shortly.', 'form': form}, status=503)
    request.session['support_ticket_refs'] = (request.session.get('support_ticket_refs', []) + [ticket.reference])[-20:]
    return redirect('ticket_confirmation', reference=ticket.reference)

def ticket_confirmation(request, reference):
    allowed = reference in request.session.get('support_ticket_refs', [])
    query = SupportTicket.objects.filter(reference=reference)
    if request.user.is_authenticated:
        query = query.filter(user=request.user)
    elif not allowed:
        query = query.none()
    ticket = get_object_or_404(query)
    return render(request, 'core/ticket_confirmation.html', {'ticket': ticket})

@require_POST
def assistant_chat(request):
    from django.conf import settings
    if _rate_limited(request, 'assistant', settings.ASSISTANT_RATE_LIMIT):
        return JsonResponse({'error': 'You are sending messages too quickly. Please wait a moment.'}, status=429)
    try:
        payload = json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Please send a valid message.'}, status=400)
    message = payload.get('message', '')
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        return JsonResponse({'error': 'Enter a message up to 2,000 characters.'}, status=400)
    result = answer_question(message.strip(), user=request.user, request=request, create_ticket=payload.get('create_ticket') is True)
    return JsonResponse(result)

@require_POST
def assistant_feedback(request):
    try:
        payload = json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid feedback.'}, status=400)
    conversation_id = payload.get('conversation_id')
    helpful = payload.get('helpful')
    comment = payload.get('comment', '')
    if not isinstance(conversation_id, str) or len(conversation_id) > 64 or not isinstance(helpful, bool) or not isinstance(comment, str):
        return JsonResponse({'error': 'Invalid feedback.'}, status=400)
    saved = save_feedback(conversation_id, helpful, comment[:500])
    return JsonResponse({'saved': saved, 'message': 'Thanks for your feedback.' if saved else 'Feedback storage is temporarily unavailable.'}, status=200 if saved else 503)

def health_check(request):
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except (OperationalError, DatabaseError):
        return JsonResponse({'status': 'unavailable', 'database': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok', 'database': 'ok'})

def home(request):
    matches = Match.objects.select_related('competition','home_team','away_team').filter(status=Match.Status.SCHEDULED, kickoff__gt=timezone.now())[:6]
    activity = Prediction.objects.select_related('match','match__home_team','match__away_team').order_by('-created_at')[:5] if request.user.is_authenticated else []
    return render(request, 'home.html', {'matches':matches,'activity':activity,'competitions':Competition.objects.filter(active=True),'live_matches':Match.objects.select_related('competition','home_team','away_team').filter(status=Match.Status.LIVE)[:3],'match_count':Match.objects.count(),'player_count':User.objects.count(),'prediction_count':Prediction.objects.count()})

def soccer_dashboard(request):
    matches = Match.objects.select_related('competition','home_team','away_team').filter(status=Match.Status.SCHEDULED, kickoff__gt=timezone.now())[:8]
    return render(request, 'soccer.html', {'matches':matches,'competitions':Competition.objects.filter(active=True)})

def matches(request):
    qs = Match.objects.select_related('competition','home_team','away_team').all()
    if request.GET.get('competition'): qs = qs.filter(competition_id=request.GET['competition'])
    if request.GET.get('status'): qs = qs.filter(status=request.GET['status'])
    if request.GET.get('date'): qs = qs.filter(kickoff__date=request.GET['date'])
    if request.GET.get('team'): qs = qs.filter(Q(home_team__name__icontains=request.GET['team'])|Q(away_team__name__icontains=request.GET['team']))
    return render(request, 'matches.html', {'matches':qs,'competitions':Competition.objects.filter(active=True),'statuses':Match.Status.choices})

def match_detail(request, pk):
    match = get_object_or_404(Match.objects.select_related('competition','home_team','away_team'),pk=pk)
    existing = Prediction.objects.filter(user=request.user, match=match).order_by('market') if request.user.is_authenticated else []
    form = PredictionForm(request.POST or None)
    if request.method == 'POST':
        if not request.user.is_authenticated: return redirect('login')
        if form.is_valid():
            try:
                place_prediction(user=request.user, match_id=match.pk, market=form.cleaned_data['market'], outcome=form.cleaned_data['outcome'], stake=form.cleaned_data['stake'])
                messages.success(request, 'Prediction submitted. Good luck!')
                return redirect('match_detail',pk=pk)
            except ValueError as exc: form.add_error(None,str(exc))
            except IntegrityError:
                duplicate = Prediction.objects.filter(user=request.user,match=match,market=form.cleaned_data['market']).exists()
                if duplicate:
                    form.add_error(None, 'You have already submitted a prediction for that market.')
                else:
                    raise
    return render(request,'match_detail.html',{'match':match,'prediction':existing,'form':form,'now':timezone.now()})

def register(request):
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            # The username may be claimed after form validation. Keep the user,
            # wallet, and welcome-credit transaction in one database transaction.
            with transaction.atomic():
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    email=form.cleaned_data['email'],
                    password=form.cleaned_data['password'],
                )
        except IntegrityError:
            # Only turn a real username collision into a form error. Preserve
            # visibility of unrelated database integrity problems.
            if User._default_manager.filter(username=form.cleaned_data['username']).exists():
                form.add_error('username', 'That username is unavailable. Please choose another.')
                return render(request, 'register.html', {'form': form})
            raise
        login(request,user)
        messages.success(request,'Welcome to GoalBet. Your 1,000 virtual credits are ready.')
        return redirect('dashboard')
    return render(request,'register.html',{'form':form})

@login_required
def dashboard(request):
    preds = request.user.predictions.select_related('match','match__home_team','match__away_team')
    total=preds.count(); settled=preds.filter(status__in=['won','lost']).count(); won=preds.filter(status='won').count()
    return render(request,'dashboard.html',{'predictions':preds[:8],'f1_predictions':request.user.f1_predictions.select_related('session__grand_prix','selected_driver')[:8],'total':total+request.user.f1_predictions.count(),'won':won+request.user.f1_predictions.filter(status='won').count(),'lost':preds.filter(status='lost').count()+request.user.f1_predictions.filter(status='lost').count(),'settled':settled+request.user.f1_predictions.filter(status__in=['won','lost']).count(),'accuracy':round((won+request.user.f1_predictions.filter(status='won').count())*100/(settled+request.user.f1_predictions.filter(status__in=['won','lost']).count())) if (settled+request.user.f1_predictions.filter(status__in=['won','lost']).count()) else 0,'transactions':request.user.wallet.transactions.all()[:6]})

@login_required
def history(request):
    page=Paginator(request.user.predictions.select_related('match','match__home_team','match__away_team'),15).get_page(request.GET.get('page'))
    return render(request,'prediction_history.html',{'page':page})

@login_required
def all_predictions(request):
    soccer = request.user.predictions.select_related('match','match__home_team','match__away_team')[:15]
    f1 = request.user.f1_predictions.select_related('session__grand_prix','selected_driver','selected_driver__constructor')[:15]
    return render(request, 'predictions.html', {'soccer_predictions':soccer,'f1_predictions':f1})

def leaderboard(request):
    soccer_settled=Count('predictions',filter=Q(predictions__status__in=['won','lost']),distinct=True)
    soccer_won=Count('predictions',filter=Q(predictions__status='won'),distinct=True)
    f1_settled=Count('f1_predictions',filter=Q(f1_predictions__status__in=['won','lost']),distinct=True)
    f1_won=Count('f1_predictions',filter=Q(f1_predictions__status='won'),distinct=True)
    users=User.objects.annotate(soccer_settled=soccer_settled,soccer_won=soccer_won,f1_settled=f1_settled,f1_won=f1_won).annotate(settled=F('soccer_settled')+F('f1_settled'),correct=F('soccer_won')+F('f1_won')).filter(settled__gte=3).annotate(accuracy=ExpressionWrapper(F('correct') * 100.0 / F('settled'), output_field=FloatField())).order_by('-accuracy','-settled','username')[:50]
    return render(request,'leaderboard.html',{'users':users})
