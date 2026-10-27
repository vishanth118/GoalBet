from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from football.models import Competition, Match, Team, Source

class Command(BaseCommand):
    help = 'Load clearly simulated GoalBet demonstration fixtures.'
    def handle(self, *args, **options):
        leagues = ['GoalBet Demo League', 'DEMO - English Premier League', 'DEMO - UEFA Champions League', 'DEMO - La Liga', 'DEMO - Serie A', 'DEMO - Bundesliga', 'DEMO - Ligue 1', 'DEMO - International Cup']
        competitions = [Competition.objects.get_or_create(name=name, defaults={'country':'DEMO / Simulation','active':True,'source':Source.DEMO})[0] for name in leagues]
        league = competitions[0]
        names = [('Northbridge FC','NBR'),('Harbor United','HBR'),('Redwood Athletic','RWD'),('Summit City','SUM'),('Lakeside Rovers','LAK'),('Eastvale Town','EAS')]
        teams = [Team.objects.get_or_create(name=name, defaults={'short_name':short,'country':'Simulation','source':Source.DEMO})[0] for name,short in names]
        now = timezone.now()
        fixtures = [(0,1,1),(2,3,2),(4,5,3),(1,2,4),(3,4,5)]
        for home, away, days in fixtures:
            Match.objects.get_or_create(competition=league, home_team=teams[home], away_team=teams[away], defaults={'kickoff':now+timedelta(days=days),'source':Source.DEMO})
        for index, competition in enumerate(competitions[1:]):
            Match.objects.get_or_create(competition=competition, home_team=teams[index % len(teams)], away_team=teams[(index + 1) % len(teams)], defaults={'kickoff':now+timedelta(days=index + 2),'source':Source.DEMO})
        # Deliberately labelled sample result, for illustrating completed-match screens.
        Match.objects.get_or_create(competition=league, home_team=teams[0], away_team=teams[3], defaults={'kickoff':now-timedelta(days=1),'status':Match.Status.COMPLETED,'home_score':2,'away_score':1,'source':Source.DEMO})
        self.stdout.write(self.style.SUCCESS('Loaded simulated GoalBet demonstration fixtures.'))
