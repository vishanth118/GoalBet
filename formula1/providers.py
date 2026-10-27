"""OpenF1 historical/live adapter.

Historical REST data (2023+) is queried without credentials. Live calls use the
server-side OAuth credentials described at https://openf1.org/auth.html.
"""
import hashlib
import json
import os
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from football.models import ProviderSyncStatus
from .models import (Circuit, Constructor, Driver, F1ChampionshipStanding, GrandPrix,
                    LapRecord, PitStop, RaceControlEvent, RaceResult, Session,
                    Source, WeatherObservation)

BASE_URL='https://api.openf1.org/v1'
TOKEN_URL='https://api.openf1.org/token'

class OpenF1Error(Exception): pass
class OpenF1NotConfigured(OpenF1Error): pass
class OpenF1RateLimited(OpenF1Error): pass
class OpenF1Unavailable(OpenF1Error): pass

class OpenF1Client:
    def __init__(self, timeout=None):
        self.timeout=float(timeout or os.environ.get('F1_API_TIMEOUT','8'))

    @property
    def live_access_configured(self):
        return bool(settings.OPENF1_USERNAME and settings.OPENF1_PASSWORD)

    def _token(self):
        if not self.live_access_configured:
            raise OpenF1NotConfigured('Historical OpenF1 data is public. Live access requires subscription credentials in OPENF1_USERNAME and OPENF1_PASSWORD.')
        token=cache.get('openf1:oauth-token')
        if token: return token
        body=urlencode({'username':settings.OPENF1_USERNAME,'password':settings.OPENF1_PASSWORD}).encode()
        request=Request(TOKEN_URL,data=body,headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'},method='POST')
        try:
            with urlopen(request,timeout=self.timeout) as response: payload=json.loads(response.read().decode('utf-8'))
        except (HTTPError,URLError,TimeoutError,OSError,ValueError):
            raise OpenF1Unavailable('OpenF1 authentication failed or timed out; check provider access and credentials.') from None
        token=payload.get('access_token') if isinstance(payload,dict) else None
        if not token: raise OpenF1Unavailable('OpenF1 did not return an access token.')
        cache.set('openf1:oauth-token',token,3300)
        return token

    def get(self, endpoint, params=None, *, ttl=3600, authenticated=False):
        params=params or {}
        canonical=json.dumps([endpoint,sorted(params.items()),authenticated],separators=(',',':'))
        key='openf1:'+hashlib.sha256(canonical.encode()).hexdigest()
        cached=cache.get(key)
        if cached is not None: return cached
        url=f'{BASE_URL}/{endpoint.lstrip("/")}'
        if params: url += '?' + urlencode(params)
        headers={'Accept':'application/json'}
        if authenticated: headers['Authorization']=f'Bearer {self._token()}'
        try:
            with urlopen(Request(url,headers=headers,method='GET'),timeout=self.timeout) as response: payload=json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            if error.code==429: raise OpenF1RateLimited('OpenF1 request rate limit reached.') from None
            if error.code in (401,403): raise OpenF1Unavailable('OpenF1 denied this request; live data may require an active subscription.') from None
            raise OpenF1Unavailable(f'OpenF1 returned HTTP {error.code}.') from None
        except (URLError,TimeoutError,OSError,ValueError,UnicodeDecodeError):
            raise OpenF1Unavailable('OpenF1 is temporarily unavailable or returned invalid data.') from None
        if not isinstance(payload,list): raise OpenF1Unavailable('OpenF1 returned an unexpected response.')
        cache.set(key,payload,ttl)
        return payload

def _parse_datetime(value):
    if not value: return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
    except (ValueError,TypeError): return None

def _status(resource,text=''):
    record,_=ProviderSyncStatus.objects.get_or_create(provider='openf1',resource=resource)
    record.last_attempt=timezone.now(); record.records_synced=0; record.error_message=text[:300]
    if not text: record.last_success=record.last_attempt
    record.save(update_fields=['last_attempt','records_synced','error_message','last_success'])
    return record

def _record_count(resource,count):
    record,_=ProviderSyncStatus.objects.get_or_create(provider='openf1',resource=resource)
    record.last_attempt=timezone.now();record.last_success=record.last_attempt;record.records_synced=count;record.error_message=''
    record.save(update_fields=['last_attempt','last_success','records_synced','error_message'])

def _session_type(row):
    raw=(row.get('session_type') or row.get('session_name') or '').lower()
    name=(row.get('session_name') or '').lower()
    if 'practice' in raw: return Session.Type.PRACTICE
    if 'sprint' in raw and ('qualifying' in raw or 'shootout' in raw): return Session.Type.SPRINT_QUALIFYING
    if 'sprint' in raw: return Session.Type.SPRINT
    if 'qualifying' in raw: return Session.Type.QUALIFYING
    if 'race' in raw or 'grand prix' in name: return Session.Type.GRAND_PRIX
    return None

def _sequence(row):
    name=row.get('session_name') or ''
    digits=''.join(ch for ch in name if ch.isdigit())
    return int(digits) if digits else 1

def sync_calendar(*, year=None, client=None):
    client=client or OpenF1Client()
    year=year or timezone.localdate().year
    if int(year)<2023: raise ValueError('OpenF1 public historical coverage begins in 2023.')
    meetings=client.get('meetings',{'year':int(year)},ttl=86400)
    sessions=client.get('sessions',{'year':int(year)},ttl=86400)
    meetings=sorted(meetings,key=lambda x:x.get('date_start') or '')
    by_meeting={}
    for order,data in enumerate(meetings,start=1):
        key=data.get('meeting_key')
        if key is None: continue
        circuit,_=Circuit.objects.update_or_create(source=Source.OPENF1,provider_id=str(data.get('circuit_key') or key),defaults={'name':data.get('circuit_short_name') or data.get('meeting_name') or 'Circuit','locality':data.get('location') or '','country':data.get('country_name') or '', 'image':data.get('circuit_image') or '', 'synced_at':timezone.now()})
        start=_parse_datetime(data.get('date_start')); end=_parse_datetime(data.get('date_end'))
        gp,_=GrandPrix.objects.update_or_create(source=Source.OPENF1,provider_id=str(key),defaults={'name':data.get('meeting_name') or data.get('meeting_official_name') or 'Grand Prix','season':int(data.get('year') or year),'round_number':order,'circuit':circuit,'demo':False,'date_start':start,'date_end':end,'gmt_offset':data.get('gmt_offset') or '', 'synced_at':timezone.now()})
        by_meeting[str(key)]=gp
    now=timezone.now(); session_count=0
    for data in sessions:
        meeting_key=str(data.get('meeting_key') or '')
        gp=by_meeting.get(meeting_key)
        kind=_session_type(data)
        session_key=data.get('session_key')
        if not gp or not kind or session_key is None: continue
        start=_parse_datetime(data.get('date_start'))
        end=_parse_datetime(data.get('date_end'))
        if data.get('is_cancelled'): state=Session.Status.CANCELLED
        elif start and start>now: state=Session.Status.SCHEDULED
        elif end and end<now: state=Session.Status.UNAVAILABLE
        else: state=Session.Status.UNAVAILABLE
        Session.objects.update_or_create(source=Source.OPENF1,provider_id=str(session_key),defaults={'grand_prix':gp,'session_type':kind,'sequence':_sequence(data),'start_time':start or gp.date_start or now,'status':state,'provider_data':data,'synced_at':now})
        session_count+=1
    _record_count(f'calendar:{year}',len(meetings)+session_count)
    return {'meetings':len(meetings),'sessions':session_count}

def _get_or_sync_driver(data, year):
    number=data.get('driver_number')
    if number is None: return None
    team_name=data.get('team_name') or 'Constructor unavailable'
    team_key=f'{year}:{team_name}'
    constructor,_=Constructor.objects.update_or_create(source=Source.OPENF1,provider_id=team_key,defaults={'name':team_name,'nationality':'','color':'#'+str(data.get('team_colour') or '555555').lstrip('#'),'synced_at':timezone.now()})
    abbreviation=data.get('name_acronym') or '---'
    driver_key=f'{year}:{number}'
    driver,_=Driver.objects.update_or_create(source=Source.OPENF1,provider_id=driver_key,defaults={'name':data.get('full_name') or data.get('broadcast_name') or f'Driver {number}','abbreviation':abbreviation[:3],'number':int(number),'nationality':data.get('country_code') or '', 'constructor':constructor,'image':data.get('headshot_url') or '', 'active':True,'synced_at':timezone.now()})
    return driver

@transaction.atomic
def sync_session_details(session, *, client=None, include_telemetry=False):
    client=client or OpenF1Client()
    if session.source!=Source.OPENF1: raise ValueError('Only OpenF1 sessions can be synchronized from this provider.')
    year=session.grand_prix.season
    driver_rows=client.get('drivers',{'session_key':session.provider_id},ttl=86400)
    drivers={int(row['driver_number']):_get_or_sync_driver(row,year) for row in driver_rows if row.get('driver_number') is not None}
    if drivers:
        session.grand_prix.drivers.add(*drivers.values())
    results=client.get('session_result',{'session_key':session.provider_id},ttl=3600)
    if results:
        for row in results:
            driver=drivers.get(int(row.get('driver_number') or -1))
            if not driver: continue
            dsq=bool(row.get('dsq')); dns=bool(row.get('dns')); dnf=bool(row.get('dnf'))
            status=RaceResult.Status.DISQUALIFIED if dsq else RaceResult.Status.DID_NOT_START if dns else RaceResult.Status.RETIRED if dnf else RaceResult.Status.FINISHED
            RaceResult.objects.update_or_create(session=session,driver=driver,defaults={'constructor':driver.constructor,'position':row.get('position'),'points':None,'status':status,'provider_data':row})
        session.status=Session.Status.COMPLETED
        session.save(update_fields=['status'])
    elif session.start_time<=timezone.now():
        session.status=Session.Status.UNAVAILABLE
        session.save(update_fields=['status'])
    if session.session_type==Session.Type.GRAND_PRIX and results:
        _sync_championship(session,client,drivers)
        if include_telemetry:
            _sync_telemetry(session,client,drivers)
    elif session.session_type==Session.Type.QUALIFYING and results:
        _sync_championship(session,client,drivers,kind='qualifying')
    session.synced_at=timezone.now();session.save(update_fields=['synced_at'])
    return len(results)

def _sync_championship(session,client,drivers,kind='race'):
    year=session.grand_prix.season
    if kind=='qualifying': return
    driver_rows=client.get('championship_drivers',{'session_key':session.provider_id},ttl=86400)
    for row in driver_rows:
        driver=drivers.get(int(row.get('driver_number') or -1))
        if not driver: continue
        start=row.get('points_start'); current=row.get('points_current')
        F1ChampionshipStanding.objects.update_or_create(session=session,kind=F1ChampionshipStanding.Kind.DRIVER,provider_id=str(row.get('driver_number')),defaults={'entity_name':driver.name,'position':row.get('position_current'),'points_start':start,'points_current':current,'driver':driver})
        if start is not None and current is not None:
            RaceResult.objects.filter(session=session,driver=driver).update(points=Decimal(str(current))-Decimal(str(start)))
    team_rows=client.get('championship_teams',{'session_key':session.provider_id},ttl=86400)
    for row in team_rows:
        name=row.get('team_name') or ''
        team=Constructor.objects.filter(source=Source.OPENF1,provider_id=f'{year}:{name}').first()
        F1ChampionshipStanding.objects.update_or_create(session=session,kind=F1ChampionshipStanding.Kind.CONSTRUCTOR,provider_id=name,defaults={'entity_name':name,'position':row.get('position_current'),'points_start':row.get('points_start'),'points_current':row.get('points_current'),'constructor':team})

def _sync_telemetry(session,client,drivers):
    laps=client.get('laps',{'session_key':session.provider_id},ttl=86400)
    best={}
    for row in laps:
        number=row.get('driver_number'); driver=drivers.get(int(number or -1))
        if not driver: continue
        lap_no=row.get('lap_number')
        try: duration=Decimal(str(row.get('lap_duration'))) if row.get('lap_duration') is not None else None
        except InvalidOperation: duration=None
        if lap_no:
            LapRecord.objects.update_or_create(session=session,driver=driver,lap_number=lap_no,defaults={'duration_seconds':duration,'is_pit_out':bool(row.get('is_pit_out_lap')),'payload':row})
        if duration is not None and not row.get('is_pit_out_lap'):
            if driver.pk not in best or duration<best[driver.pk]: best[driver.pk]=duration
    if best:
        fastest=min(best.values())
        for driver_id,duration in best.items():
            RaceResult.objects.filter(session=session,driver_id=driver_id).update(fastest_lap=(duration==fastest),fastest_lap_known=True)
    for row in client.get('pit',{'session_key':session.provider_id},ttl=86400):
        driver=drivers.get(int(row.get('driver_number') or -1))
        if not driver: continue
        lap=row.get('lap_number'); duration=row.get('stop_duration')
        try: duration=Decimal(str(duration)) if duration is not None else None
        except InvalidOperation: duration=None
        occurred=_parse_datetime(row.get('date'))
        PitStop.objects.update_or_create(session=session,driver=driver,lap_number=lap,defaults={'stop_duration':duration,'occurred_at':occurred,'payload':row})
    for index,row in enumerate(client.get('race_control',{'session_key':session.provider_id},ttl=3600)):
        occurred=_parse_datetime(row.get('date')); key=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
        number=row.get('driver_number'); driver=drivers.get(int(number)) if number is not None else None
        RaceControlEvent.objects.update_or_create(session=session,provider_id=key,defaults={'occurred_at':occurred,'category':row.get('category') or '', 'flag':row.get('flag') or '', 'message':row.get('message') or '', 'driver':driver,'payload':row})
    for row in client.get('weather',{'session_key':session.provider_id},ttl=120):
        observed=_parse_datetime(row.get('date'))
        if not observed: continue
        def dec(key):
            try: return Decimal(str(row[key])) if row.get(key) is not None else None
            except InvalidOperation: return None
        WeatherObservation.objects.update_or_create(session=session,observed_at=observed,defaults={'air_temperature':dec('air_temperature'),'track_temperature':dec('track_temperature'),'rainfall':bool(row.get('rainfall')) if row.get('rainfall') is not None else None,'payload':row})

def sync_live_status(session, *, client=None):
    client=client or OpenF1Client()
    if not client.live_access_configured:
        session.status=Session.Status.UNAVAILABLE;session.save(update_fields=['status']);return session.status
    events=client.get('race_control',{'session_key':session.provider_id},ttl=5,authenticated=True)
    messages=[(item.get('message') or '').lower() for item in events if item.get('category')=='SessionStatus']
    if any('started' in message for message in messages) and not any(('finished' in message or 'ended' in message) for message in messages):
        session.status=Session.Status.LIVE
    elif any('finished' in message or 'ended' in message for message in messages):
        session.status=Session.Status.COMPLETED
    else:
        session.status=Session.Status.UNAVAILABLE
    session.synced_at=timezone.now();session.save(update_fields=['status','synced_at'])
    return session.status

def sync_f1_data(*, year=None, include_details=False, include_live=False, client=None):
    client=client or OpenF1Client()
    year=int(year or timezone.localdate().year)
    try:
        counts=sync_calendar(year=year,client=client)
        detail_count=0
        if include_details:
            completed=Session.objects.filter(source=Source.OPENF1,grand_prix__season=year,session_type=Session.Type.GRAND_PRIX,start_time__lt=timezone.now()).order_by('-start_time')[:4]
            for session in completed:
                try: detail_count+=sync_session_details(session,client=client,include_telemetry=True)
                except OpenF1Error as error: _status(f'detail:{session.provider_id}',str(error))
        live_status=None
        if include_live:
            current=Session.objects.filter(source=Source.OPENF1,start_time__lte=timezone.now()+timedelta(minutes=30),start_time__gte=timezone.now()-timedelta(hours=5)).order_by('start_time').first()
            if current: live_status=sync_live_status(current,client=client)
        _record_count(f'sync:{year}',counts['meetings']+counts['sessions']+detail_count)
        return {**counts,'results':detail_count,'live_status':live_status}
    except OpenF1Error as error:
        _status(f'sync:{year}',str(error));raise
