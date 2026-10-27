"""Transparent statistical baselines; never trained on DEMO/manual records."""
from collections import defaultdict
from datetime import timedelta
import math

from django.db.models import Q
from django.utils import timezone

from football.models import Match, Source as SoccerSource
from formula1.models import GrandPrix, RaceResult, Session, Source as F1Source

SOCCER_MODEL_VERSION = 'poisson-home-away-v1'
F1_MODEL_VERSION = 'recent-results-frequency-v1'
MIN_TEAM_MATCHES = 5
MIN_F1_RACES = 5

def _poisson(mean, maximum=10):
    if mean <= 0:
        return [1.0] + [0.0] * maximum
    values=[]
    for goals in range(maximum+1):
        values.append(math.exp(-mean) * mean**goals / math.factorial(goals))
    total=sum(values)
    return [value/total for value in values]

def analyze_soccer_match(match):
    """Estimate match markets using prior API-Football results only.

    Independent Poisson scoring rates use the last ten home/away observations
    per side. Fixtures must be played strictly before the target kickoff.
    """
    if match.source != SoccerSource.API_FOOTBALL or match.status != Match.Status.SCHEDULED:
        return {'status':'unavailable','model_version':SOCCER_MODEL_VERSION,'message':'Analysis is restricted to scheduled provider-sourced Soccer matches.'}
    prior=Match.objects.filter(source=SoccerSource.API_FOOTBALL,status=Match.Status.COMPLETED,kickoff__lt=match.kickoff,competition=match.competition).exclude(home_score__isnull=True).exclude(away_score__isnull=True)
    home_for=list(prior.filter(home_team=match.home_team).order_by('-kickoff').values_list('home_score',flat=True)[:10])
    home_against=list(prior.filter(home_team=match.home_team).order_by('-kickoff').values_list('away_score',flat=True)[:10])
    away_for=list(prior.filter(away_team=match.away_team).order_by('-kickoff').values_list('away_score',flat=True)[:10])
    away_against=list(prior.filter(away_team=match.away_team).order_by('-kickoff').values_list('home_score',flat=True)[:10])
    samples={'home_team_home_matches':len(home_for),'away_team_away_matches':len(away_for)}
    if min(len(home_for),len(home_against),len(away_for),len(away_against)) < MIN_TEAM_MATCHES:
        return {'status':'insufficient','model_version':SOCCER_MODEL_VERSION,'sample_size':min(len(home_for),len(away_for)),'samples':samples,'message':f'At least {MIN_TEAM_MATCHES} prior home and away matches per side are required. No probability is shown.'}
    expected_home=(sum(home_for)/len(home_for)+sum(away_against)/len(away_against))/2
    expected_away=(sum(away_for)/len(away_for)+sum(home_against)/len(home_against))/2
    home_dist=_poisson(expected_home); away_dist=_poisson(expected_away)
    grid={(h,a):home_dist[h]*away_dist[a] for h in range(len(home_dist)) for a in range(len(away_dist))}
    totals=sum(grid.values()) or 1
    home_win=sum(v for (h,a),v in grid.items() if h>a)/totals
    draw=sum(v for (h,a),v in grid.items() if h==a)/totals
    away_win=sum(v for (h,a),v in grid.items() if h<a)/totals
    btts=sum(v for (h,a),v in grid.items() if h>0 and a>0)/totals
    over=sum(v for (h,a),v in grid.items() if h+a>=3)/totals
    return {'status':'ready','model_version':SOCCER_MODEL_VERSION,'sample_size':min(len(home_for),len(home_against),len(away_for),len(away_against)),'samples':samples,'expected_goals':{'home':round(expected_home,3),'away':round(expected_away,3)},'probabilities':{'home_win':round(home_win,6),'draw':round(draw,6),'away_win':round(away_win,6),'both_teams_score_yes':round(btts,6),'over_2_5':round(over,6)},'data_as_of':timezone.now().isoformat(),'limitations':['Independent Poisson goals model; no injury or lineup feature is used.','Probabilities are estimates, not guarantees.']}

def analyze_f1_race(grand_prix):
    if grand_prix.source != F1Source.OPENF1 or grand_prix.demo:
        return {'status':'unavailable','model_version':F1_MODEL_VERSION,'message':'Analysis is restricted to OpenF1 provider-sourced race weekends.'}
    previous=GrandPrix.objects.filter(source=F1Source.OPENF1,demo=False,season=grand_prix.season,date_start__lt=grand_prix.date_start).order_by('-date_start')[:MIN_F1_RACES]
    races=list(previous)
    if len(races)<MIN_F1_RACES:
        return {'status':'insufficient','model_version':F1_MODEL_VERSION,'sample_size':len(races),'message':f'At least {MIN_F1_RACES} earlier OpenF1 races are required. No probability is shown.'}
    drivers=list(grand_prix.drivers.filter(source=F1Source.OPENF1,active=True))
    if not drivers:
        return {'status':'insufficient','model_version':F1_MODEL_VERSION,'sample_size':0,'message':'No provider driver entry list is available.'}
    race_ids=set(r.pk for r in races)
    results=RaceResult.objects.filter(session__grand_prix_id__in=race_ids,session__grand_prix__source=F1Source.OPENF1,session__session_type=Session.Type.GRAND_PRIX,session__status=Session.Status.COMPLETED,driver__source=F1Source.OPENF1,status=RaceResult.Status.FINISHED).select_related('session__grand_prix')
    by_driver=defaultdict(list)
    for result in results:
        by_driver[result.driver_id].append(result)
    if any(len(by_driver[d.pk])<MIN_F1_RACES for d in drivers):
        return {'status':'insufficient','model_version':F1_MODEL_VERSION,'sample_size':len(races),'message':'Historical classifications do not cover every entered driver for five earlier races.'}
    win_counts={d.pk:sum(1 for r in by_driver[d.pk] if r.position==1) for d in drivers}
    podium_counts={d.pk:sum(1 for r in by_driver[d.pk] if r.position is not None and r.position<=3) for d in drivers}
    win_total=sum(win_counts.values()) or 1
    probabilities={d.provider_id:{'driver':d.name,'race_winner':round(win_counts[d.pk]/win_total,6),'podium':round(podium_counts[d.pk]/MIN_F1_RACES,6),'recent_results':[r.position for r in sorted(by_driver[d.pk],key=lambda r:r.session.grand_prix.date_start or timezone.now(),reverse=True)[:MIN_F1_RACES]]} for d in drivers}
    return {'status':'ready','model_version':F1_MODEL_VERSION,'sample_size':len(races),'probabilities':probabilities,'data_as_of':timezone.now().isoformat(),'limitations':['Empirical frequencies over five prior races; no qualifying, weather, tyre or pit-stop inputs are used.','Probabilities are estimates, not guarantees.']}
