"""Server-side API-Football adapter, cache, and persistence layer.

Official API docs: https://www.api-football.com/documentation-v3
All HTTP calls are GET-only, time-limited, and authenticated with the server key.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import (Competition, Match, MatchEvent, MatchLineup, MatchPlayerStatistics,
                     MatchStatistics, Player, PlayerSeasonStats, ProviderSyncStatus,
                     Season, SeasonStanding, Source, Team)

BASE_URL = 'https://v3.football.api-sports.io'

class SportsProviderError(Exception): pass
class ProviderNotConfigured(SportsProviderError): pass
class ProviderRateLimited(SportsProviderError): pass
class ProviderUnavailable(SportsProviderError): pass
class ProviderPayloadError(SportsProviderError): pass

class APIFootballClient:
    def __init__(self, api_key=None, timeout=None):
        self.api_key = api_key or os.environ.get('SOCCER_API_KEY') or os.environ.get('SOCCER_DATA_API_KEY')
        self.timeout = float(timeout or os.environ.get('SOCCER_API_TIMEOUT', '8'))
        self.last_paging = {'current':1,'total':1}

    def get(self, endpoint, params=None, ttl=3600, use_cache=True):
        if not self.api_key:
            raise ProviderNotConfigured('Set SOCCER_API_KEY to enable live Soccer provider data.')
        params = params or {}
        canonical = json.dumps([endpoint, sorted(params.items())], separators=(',', ':'))
        cache_key = 'api_football:' + hashlib.sha256(canonical.encode()).hexdigest()
        if use_cache:
            value = cache.get(cache_key)
            if value is not None:
                return value
        url = f'{BASE_URL}/{endpoint.lstrip("/")}'
        if params:
            url += '?' + urlencode(params)
        req = Request(url, headers={'x-apisports-key': self.api_key, 'Accept': 'application/json'}, method='GET')
        try:
            with urlopen(req, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            if error.code == 429:
                raise ProviderRateLimited('Soccer provider rate limit reached; retry after its quota resets.') from None
            raise ProviderUnavailable(f'Soccer provider returned HTTP {error.code}.') from None
        except (URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailable('Soccer provider is temporarily unavailable.') from None
        except (ValueError, UnicodeDecodeError):
            raise ProviderPayloadError('Soccer provider returned an unreadable response.') from None
        if not isinstance(payload, dict):
            raise ProviderPayloadError('Soccer provider returned an unexpected response.')
        errors = payload.get('errors')
        if errors:
            message = ', '.join(str(v) for v in errors.values()) if isinstance(errors, dict) else '; '.join(map(str, errors))
            if 'rate' in message.lower() or 'requests' in message.lower():
                raise ProviderRateLimited('Soccer provider rate limit reached.')
            raise ProviderUnavailable(f'Soccer provider rejected the request: {message[:180]}')
        result = payload.get('response', [])
        self.last_paging = payload.get('paging') or {'current':1,'total':1}
        if not isinstance(result, list):
            raise ProviderPayloadError('Soccer provider response list is missing.')
        if use_cache:
            cache.set(cache_key, result, ttl)
        return result

def _sync_status(resource, *, count=0, error=''):
    status, _ = ProviderSyncStatus.objects.get_or_create(provider='api_football', resource=resource)
    status.last_attempt = timezone.now()
    status.records_synced = count
    status.error_message = error[:300]
    if not error:
        status.last_success = status.last_attempt
    status.save(update_fields=['last_attempt','records_synced','error_message','last_success'])

def _provider_object(model, provider_id, defaults):
    obj, _ = model.objects.update_or_create(source=Source.API_FOOTBALL, provider_id=str(provider_id), defaults=defaults)
    return obj

def sync_competitions(client=None):
    client = client or APIFootballClient()
    count = 0
    try:
        page = 1
        while page <= int(os.environ.get('SOCCER_LEAGUE_PAGE_LIMIT','10')):
            rows = client.get('leagues', {'current':'true','page':page}, ttl=43200)
            for row in rows:
                league = row.get('league') or {}
                country = row.get('country') or {}
                if not league.get('id'):
                    continue
                comp = _provider_object(Competition, league['id'], {'name':league.get('name') or 'Competition','country':country.get('name') or 'Unknown','logo':league.get('logo') or '', 'active':True,'synced_at':timezone.now()})
                for season_row in row.get('seasons') or []:
                    year = season_row.get('year')
                    if year:
                        Season.objects.update_or_create(competition=comp,year=year,defaults={'current':bool(season_row.get('current')),'source':Source.API_FOOTBALL,'provider_id':str(year),'synced_at':timezone.now()})
                count += 1
            if not rows or page >= int(client.last_paging.get('total',page)):
                break
            page += 1
        _sync_status('competitions',count=count)
        return count
    except SportsProviderError as error:
        _sync_status('competitions',count=count,error=str(error))
        raise

def _upsert_team(obj):
    if not obj or not obj.get('id'):
        return None
    return _provider_object(Team,obj['id'],{'name':obj.get('name') or 'Team','short_name':obj.get('code') or (obj.get('name') or 'TEAM')[:12],'logo':obj.get('logo') or '', 'country':obj.get('country') or '','synced_at':timezone.now()})

def _season_for_fixture(competition_data):
    comp_id=competition_data.get('id'); year=competition_data.get('season')
    if not comp_id or not year: return None
    comp=Competition.objects.filter(source=Source.API_FOOTBALL,provider_id=str(comp_id)).first()
    if comp is None: return None
    season,_=Season.objects.get_or_create(competition=comp,year=year,defaults={'source':Source.API_FOOTBALL,'provider_id':str(year)})
    return season

def _map_status(short):
    short=(short or '').upper()
    if short in {'1H','HT','2H','ET','BT','P','LIVE','INT'}: return Match.Status.LIVE
    if short in {'FT','AET','PEN'}: return Match.Status.COMPLETED
    if short in {'PST','SUSP'}: return Match.Status.POSTPONED
    if short in {'CANC','ABD'}: return Match.Status.CANCELLED
    return Match.Status.SCHEDULED

def _save_fixture(row):
    fixture=row.get('fixture') or {}; teams=row.get('teams') or {}; goals=row.get('goals') or {}; league=row.get('league') or {}
    fixture_id=fixture.get('id')
    if not fixture_id: return None
    home=_upsert_team(teams.get('home')); away=_upsert_team(teams.get('away'))
    if not home or not away: return None
    when=fixture.get('date')
    try: kickoff=datetime.fromisoformat(when.replace('Z','+00:00'))
    except (ValueError,AttributeError): return None
    status_obj=fixture.get('status') or {}
    competition=Competition.objects.filter(source=Source.API_FOOTBALL,provider_id=str(league.get('id'))).first()
    if competition is None:
        competition=_provider_object(Competition,league['id'],{'name':league.get('name') or 'Competition','country':'','logo':league.get('logo') or '', 'active':True,'synced_at':timezone.now()})
    season=_season_for_fixture(league)
    match,_=Match.objects.update_or_create(source=Source.API_FOOTBALL,provider_id=str(fixture_id),defaults={
        'competition':competition,'home_team':home,'away_team':away,'kickoff':kickoff,'status':_map_status(status_obj.get('short')),
        'home_score':goals.get('home'),'away_score':goals.get('away'),'season':season,'venue':(fixture.get('venue') or {}).get('name') or '',
        'round_name':league.get('round') or '', 'elapsed':status_obj.get('elapsed'),'provider_status':status_obj.get('long') or status_obj.get('short') or '',
        'provider_data':row,'synced_at':timezone.now()})
    return match

def sync_fixtures(*, client=None, include_live=True, days_back=10, days_forward=21):
    client=client or APIFootballClient()
    today=timezone.localdate()
    date_from=today-timedelta(days=days_back); date_to=today+timedelta(days=days_forward)
    rows=client.get('fixtures',{'from':date_from.isoformat(),'to':date_to.isoformat(),'timezone':'UTC'},ttl=120)
    if include_live:
        rows += client.get('fixtures',{'live':'all','timezone':'UTC'},ttl=20)
    count=0; seen=set()
    for row in rows:
        key=(row.get('fixture') or {}).get('id')
        if key in seen: continue
        seen.add(key)
        if _save_fixture(row): count += 1
    _sync_status('fixtures',count=count)
    return count

def sync_standings(season=None):
    season=season or Season.objects.filter(source=Source.API_FOOTBALL,current=True).order_by('-year').first()
    if season is None: return 0
    client=APIFootballClient()
    data=client.get('standings',{'league':season.competition.provider_id,'season':season.year},ttl=3600)
    count=0
    try:
        groups=data[0]['league']['standings']
    except (IndexError,KeyError,TypeError):
        _sync_status(f'standings:{season.pk}',count=0,error='Provider has no standings for this competition/season.')
        return 0
    for group in groups:
        for entry in group:
            team=_upsert_team(entry.get('team') or {})
            if not team: continue
            all_stats=entry.get('all') or {}; goals=all_stats.get('goals') or {}
            SeasonStanding.objects.update_or_create(season=season,team=team,defaults={'rank':entry.get('rank'),'points':entry.get('points'),'goals_for':goals.get('for'),'goals_against':goals.get('against'),'form':entry.get('form') or '', 'payload':entry,'source':Source.API_FOOTBALL})
            count+=1
    _sync_status(f'standings:{season.pk}',count=count)
    return count

def sync_squads(*, team_limit=12):
    client=APIFootballClient(); teams=Team.objects.filter(source=Source.API_FOOTBALL).order_by('provider_id')[:team_limit]; count=0
    for team in teams:
        response=client.get('players/squads',{'team':team.provider_id},ttl=86400)
        for squad in response:
            for data in squad.get('players') or []:
                if not data.get('id'): continue
                Player.objects.update_or_create(source=Source.API_FOOTBALL,provider_id=str(data['id']),defaults={'name':data.get('name') or 'Player','photo':data.get('photo') or '', 'position':data.get('position') or '', 'nationality':data.get('nationality') or '', 'birth_date':(data.get('birth') or {}).get('date'),'age':data.get('age'),'shirt_number':data.get('number'),'height':data.get('height') or '', 'weight':data.get('weight') or '', 'current_team':team,'synced_at':timezone.now()})
                count+=1
    _sync_status('players:squads',count=count)
    return count

def load_match_details(match):
    """Fetch API-Football's fixture detail response for events, lineups and stats."""
    if match.source != Source.API_FOOTBALL or not match.provider_id:
        return None
    client=APIFootballClient()
    rows=client.get('fixtures',{'id':match.provider_id},ttl=120 if match.status == Match.Status.LIVE else 1800)
    if not rows: return None
    match.provider_data=rows[0]
    match.synced_at=timezone.now()
    match.save(update_fields=['provider_data','synced_at'])
    payload=rows[0]
    for group in payload.get('events') or []:
        team_data=group.get('team') or {}; team=Team.objects.filter(source=Source.API_FOOTBALL,provider_id=str(team_data.get('id'))).first()
        player_data=group.get('player') or {}; assist_data=group.get('assist') or {}
        player=Player.objects.filter(source=Source.API_FOOTBALL,provider_id=str(player_data.get('id'))).first() if player_data.get('id') else None
        assist=Player.objects.filter(source=Source.API_FOOTBALL,provider_id=str(assist_data.get('id'))).first() if assist_data.get('id') else None
        time_data=group.get('time') or {}; external=':'.join(str(x or '') for x in [time_data.get('elapsed'),time_data.get('extra'),team_data.get('id'),(group.get('player') or {}).get('id'),group.get('type'),group.get('detail')])
        MatchEvent.objects.update_or_create(match=match,provider_id=external,defaults={'elapsed':time_data.get('elapsed'),'extra_time':time_data.get('extra'),'event_type':group.get('type') or '', 'detail':group.get('detail') or '', 'comments':group.get('comments') or '', 'team':team,'player':player,'assist':assist,'source':Source.API_FOOTBALL})
    return payload

def sync_soccer_data(*, include_players=False):
    client=APIFootballClient()
    competitions=sync_competitions(client)
    fixtures=sync_fixtures(client=client)
    players=sync_squads() if include_players else 0
    return {'competitions':competitions,'fixtures':fixtures,'players':players}
