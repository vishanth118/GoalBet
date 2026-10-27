from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from predictions.models import F1Prediction
from .forms import F1PredictionForm
from .models import Constructor, Driver, GrandPrix, RaceResult, Session
from .services.prediction_settlement import place_f1_prediction

def dashboard(request):
    upcoming = GrandPrix.objects.filter(sessions__start_time__gte=timezone.now(), sessions__status=Session.Status.SCHEDULED).distinct().prefetch_related('circuit','sessions').order_by('season','round_number')
    next_gp = upcoming.first()
    latest_results = RaceResult.objects.filter(session__session_type=Session.Type.GRAND_PRIX, session__status=Session.Status.COMPLETED).select_related('driver','constructor','session__grand_prix').order_by('-session__start_time','position')[:10]
    season = next_gp.season if next_gp else GrandPrix.objects.order_by('-season').values_list('season',flat=True).first()
    source = next_gp.source if next_gp else None
    season_races = GrandPrix.objects.filter(season=season, source=source) if season and source else GrandPrix.objects.none()
    driver_count = Driver.objects.filter(grand_prix_entries__in=season_races).distinct().count() if season and source else 0
    return render(request, 'f1/dashboard.html', {
        'next_gp': next_gp,
        'sessions': next_gp.sessions.all() if next_gp else [],
        'latest_results': latest_results,
        'drivers': driver_standings(season)[:5] if season else [],
        'constructors': constructor_standings(season)[:5] if season else [],
        'season': season,
        'data_source': next_gp.get_source_display() if next_gp else '',
        'race_count': season_races.count(),
        'session_count': Session.objects.filter(grand_prix__in=season_races).count(),
        'driver_count': driver_count,
    })

def calendar(request):
    races = GrandPrix.objects.select_related('circuit').prefetch_related('sessions').order_by('-season','round_number')
    season = request.GET.get('season')
    if season and season.isdigit(): races = races.filter(season=int(season))
    return render(request, 'f1/calendar.html', {'races':races,'seasons':GrandPrix.objects.values_list('season',flat=True).distinct().order_by('-season'),'selected_season':season})

def race_detail(request, pk):
    race = get_object_or_404(GrandPrix.objects.select_related('circuit').prefetch_related('sessions__results__driver','sessions__results__constructor'),pk=pk)
    form = F1PredictionForm(request.POST if request.method == 'POST' else None, grand_prix=race)
    if request.method == 'POST':
        if not request.user.is_authenticated: return redirect('login')
        if form.is_valid():
            try:
                place_f1_prediction(user=request.user,session_id=form.cleaned_data['session'].pk,market=form.cleaned_data['market'],driver_id=form.cleaned_data['driver'].pk,stake=form.cleaned_data['stake'])
                return redirect('f1_race_detail',pk=pk)
            except ValueError as error: form.add_error(None,str(error))
            except IntegrityError:
                duplicate=F1Prediction.objects.filter(user=request.user,session=form.cleaned_data['session'],market=form.cleaned_data['market']).exists()
                if duplicate:
                    form.add_error(None,'You have already predicted this market for that session.')
                else:
                    raise
    predictions = F1Prediction.objects.filter(user=request.user,session__grand_prix=race).select_related('session','selected_driver','selected_driver__constructor') if request.user.is_authenticated else []
    posted_session = request.POST.get('session') if request.method == 'POST' else None
    session_forms = []
    for session in race.sessions.all():
        bound = request.method == 'POST' and str(session.pk) == posted_session
        session_form = form if bound else F1PredictionForm(initial={'session':session.pk}, grand_prix=race)
        session_forms.append((session, session_form))
    return render(request,'f1/race_detail.html',{'race':race,'session_forms':session_forms,'predictions':predictions,'multipliers':settings.F1_SIMULATED_MULTIPLIERS,'now':timezone.now()})

def driver_standings(season):
    return Driver.objects.filter(results__session__session_type=Session.Type.GRAND_PRIX,results__session__status=Session.Status.COMPLETED,results__session__grand_prix__season=season,results__status=RaceResult.Status.FINISHED).annotate(points=Sum('results__points'),wins=Count('results',filter=Q(results__position=1))).order_by('-points','-wins','number')

def constructor_standings(season):
    return Constructor.objects.filter(results__session__session_type=Session.Type.GRAND_PRIX,results__session__status=Session.Status.COMPLETED,results__session__grand_prix__season=season,results__status=RaceResult.Status.FINISHED).annotate(points=Sum('results__points'),wins=Count('results',filter=Q(results__position=1))).order_by('-points','-wins','name')

def standings(request):
    available=list(GrandPrix.objects.values_list('season',flat=True).distinct().order_by('-season'))
    season=request.GET.get('season')
    selected=int(season) if season and season.isdigit() else (available[0] if available else None)
    drivers=driver_standings(selected) if selected else []
    constructors=constructor_standings(selected) if selected else []
    return render(request,'f1/standings.html',{'drivers':drivers,'constructors':constructors,'seasons':available,'selected_season':selected})

def results(request):
    sessions=Session.objects.filter(status=Session.Status.COMPLETED).select_related('grand_prix','grand_prix__circuit').prefetch_related('results__driver','results__constructor').order_by('-start_time')
    return render(request,'f1/results.html',{'sessions':sessions})

@login_required
def prediction_history(request):
    page=Paginator(F1Prediction.objects.filter(user=request.user).select_related('session__grand_prix','selected_driver','selected_driver__constructor'),15).get_page(request.GET.get('page'))
    return render(request,'f1/predictions.html',{'page':page})
