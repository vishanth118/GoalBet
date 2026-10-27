from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from formula1.models import Circuit, Constructor, Driver, GrandPrix, RaceResult, Session, Source

class Command(BaseCommand):
    help = 'Load idempotent fictional Formula 1-style demo data (not official fixtures or results).'

    def handle(self, *args, **options):
        season = timezone.localdate().year
        team_specs = [
            ('DEMO Apex Motorsport', 'Simulation', '#e34b55'),
            ('DEMO Velocity Works', 'Simulation', '#55a6e8'),
        ]
        constructors = [Constructor.objects.get_or_create(name=name, source=Source.DEMO, defaults={'nationality':nationality,'color':color})[0] for name,nationality,color in team_specs]
        driver_specs = [
            ('Ari Vale','AVL',11,'Simulation',0),('Mika Rowan','MRO',27,'Simulation',0),('Tomas Reed','TRE',63,'Simulation',0),
            ('Nico Arden','NAR',84,'Simulation',1),('Luca Fen','LFE',36,'Simulation',1),('Sam Kade','SKA',52,'Simulation',1),
        ]
        drivers = []
        for name, abbreviation, number, nationality, constructor_index in driver_specs:
            driver, _ = Driver.objects.get_or_create(abbreviation=abbreviation, source=Source.DEMO, defaults={'name':name,'number':number,'nationality':nationality,'constructor':constructors[constructor_index]})
            drivers.append(driver)
        circuit, _ = Circuit.objects.get_or_create(name='DEMO Coastline Circuit', source=Source.DEMO, defaults={'locality':'Demo Bay','country':'Simulation','time_zone':'UTC','length_km':'5.250'})
        completed_gp, _ = GrandPrix.objects.get_or_create(season=season,round_number=1,source=Source.DEMO,defaults={'name':'DEMO Coastline Grand Prix','circuit':circuit,'demo':True})
        upcoming_gp, _ = GrandPrix.objects.get_or_create(season=season,round_number=2,source=Source.DEMO,defaults={'name':'DEMO Highland Grand Prix','circuit':circuit,'demo':True})
        completed_gp.drivers.add(*drivers)
        upcoming_gp.drivers.add(*drivers)
        now = timezone.now()
        completed_starts = {
            Session.Type.PRACTICE: now-timedelta(days=22),
            Session.Type.QUALIFYING: now-timedelta(days=21,hours=3),
            Session.Type.GRAND_PRIX: now-timedelta(days=21),
        }
        for session_type, start_time in completed_starts.items():
            session, _ = Session.objects.get_or_create(grand_prix=completed_gp,session_type=session_type,sequence=1,defaults={'start_time':start_time,'status':Session.Status.COMPLETED,'source':Source.DEMO})
            for position, driver in enumerate(drivers, start=1):
                points = [25,18,15,12,10,8][position-1] if session_type == Session.Type.GRAND_PRIX else 0
                RaceResult.objects.get_or_create(session=session,driver=driver,defaults={'constructor':driver.constructor,'position':position,'points':points,'status':RaceResult.Status.FINISHED,'fastest_lap':session_type == Session.Type.GRAND_PRIX and position == 4})
        weekend = [
            (Session.Type.PRACTICE,1,8,10),(Session.Type.PRACTICE,2,8,14),(Session.Type.PRACTICE,3,9,10),
            (Session.Type.SPRINT_QUALIFYING,1,9,14),(Session.Type.SPRINT,1,10,11),
            (Session.Type.QUALIFYING,1,10,15),(Session.Type.GRAND_PRIX,1,11,13),
        ]
        for session_type, sequence, day, hour in weekend:
            Session.objects.get_or_create(grand_prix=upcoming_gp,session_type=session_type,sequence=sequence,defaults={'start_time':now+timedelta(days=day,hours=hour),'status':Session.Status.SCHEDULED,'source':Source.DEMO})
        self.stdout.write(self.style.SUCCESS('Loaded fictional DEMO F1 teams, drivers, circuit, race weekend and sample classification.'))
