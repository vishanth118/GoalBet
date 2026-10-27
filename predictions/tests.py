from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command
from django.db import IntegrityError
from football.models import Competition, Team, Match
from formula1.models import Circuit, Constructor, Driver, GrandPrix, RaceResult, Session
from formula1.services.prediction_settlement import place_f1_prediction, settle_f1_session, void_f1_session
from .models import F1Prediction, Prediction, Transaction, Wallet
from .services import place_prediction, settle_match, void_match

class GoalBetTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('player', password='Strongpass123!')
        self.other = User.objects.create_user('rival', password='Strongpass123!')
        self.comp = Competition.objects.create(name='Test League', country='Test')
        self.home = Team.objects.create(name='Home', short_name='HOM', country='Test')
        self.away = Team.objects.create(name='Away', short_name='AWY', country='Test')
        self.match = Match.objects.create(competition=self.comp,home_team=self.home,away_team=self.away,kickoff=timezone.now()+timedelta(days=1))

    def test_registration_login_and_wallet_initialization(self):
        response = self.client.post(reverse('register'), {'username':'newbie','email':'new@example.test','password':'LongPass123!','confirm_password':'LongPass123!'})
        self.assertRedirects(response, reverse('dashboard'))
        wallet=Wallet.objects.get(user__username='newbie')
        self.assertEqual(wallet.balance, Decimal('1000.00'))
        created_user=User.objects.get(username='newbie')
        self.assertTrue(created_user.check_password('LongPass123!'))
        self.assertNotEqual(created_user.password, 'LongPass123!')

    def test_duplicate_username_shows_friendly_error_and_keeps_safe_values(self):
        response=self.client.post(reverse('register'), {'username':'player','email':'kept@example.test','password':'LongPass123!','confirm_password':'LongPass123!'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'That username is unavailable')
        self.assertContains(response,'kept@example.test')
        self.assertEqual(User.objects.filter(username='player').count(),1)

    def test_password_mismatch_shows_form_error(self):
        response=self.client.post(reverse('register'), {'username':'different','email':'different@example.test','password':'LongPass123!','confirm_password':'OtherPass123!'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Passwords do not match')
        self.assertFalse(User.objects.filter(username='different').exists())

    def test_password_uses_django_configured_validators(self):
        response=self.client.post(reverse('register'), {'username':'secureplayer','email':'secure@example.test','password':'password','confirm_password':'password'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'password is too common')
        self.assertFalse(User.objects.filter(username='secureplayer').exists())

    def test_invalid_registration_shows_validation_errors(self):
        response=self.client.post(reverse('register'), {'username':'','email':'not-an-email','password':'short','confirm_password':'short'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Enter a valid email address')
        self.assertContains(response,'Ensure this value has at least 8 characters')
        self.assertEqual(User.objects.count(),2)

    def test_successful_login_redirects_to_dashboard(self):
        response=self.client.post(reverse('login'), {'username':'player','password':'Strongpass123!'})
        self.assertRedirects(response, reverse('dashboard'))

    def test_failed_login_shows_friendly_error(self):
        response=self.client.post(reverse('login'), {'username':'player','password':'incorrect'})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Please enter a correct username and password')

    def test_prediction_debits_wallet_and_records_transaction(self):
        place_prediction(user=self.user,match_id=self.match.pk,outcome='home',stake=Decimal('100'))
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('900.00'))
        self.assertEqual(Transaction.objects.filter(wallet=self.user.wallet,type=Transaction.Type.STAKE).count(),1)

    def test_insufficient_balance_and_invalid_outcome_rejected(self):
        with self.assertRaisesMessage(ValueError,'enough virtual credits'):
            place_prediction(user=self.user,match_id=self.match.pk,outcome='home',stake=Decimal('1001'))
        with self.assertRaisesMessage(ValueError,'valid selection'):
            place_prediction(user=self.user,match_id=self.match.pk,outcome='score',stake=Decimal('1'))

    def test_duplicate_prediction_rejected(self):
        place_prediction(user=self.user,match_id=self.match.pk,outcome='home',stake=Decimal('1'))
        with self.assertRaises(Exception):
            place_prediction(user=self.user,match_id=self.match.pk,outcome='draw',stake=Decimal('1'))

    def test_kickoff_closes_predictions(self):
        self.match.kickoff=timezone.now()-timedelta(minutes=1); self.match.save()
        with self.assertRaisesMessage(ValueError,'before kickoff'):
            place_prediction(user=self.user,match_id=self.match.pk,outcome='home',stake=Decimal('1'))

    def test_winning_and_losing_settlement_is_idempotent(self):
        win=place_prediction(user=self.user,match_id=self.match.pk,outcome='home',stake=Decimal('100'))
        lose=place_prediction(user=self.other,match_id=self.match.pk,outcome='away',stake=Decimal('50'))
        self.match.status=Match.Status.COMPLETED; self.match.home_score=2; self.match.away_score=0; self.match.save()
        self.assertEqual(settle_match(self.match.pk),2)
        self.assertEqual(settle_match(self.match.pk),0)
        win.refresh_from_db(); lose.refresh_from_db(); self.user.wallet.refresh_from_db(); self.other.wallet.refresh_from_db()
        self.assertEqual(win.status,Prediction.Status.WON); self.assertEqual(win.profit_loss,Decimal('100.00'))
        self.assertEqual(self.user.wallet.balance,Decimal('1100.00'))
        self.assertEqual(lose.status,Prediction.Status.LOST); self.assertEqual(self.other.wallet.balance,Decimal('950.00'))

    def test_void_refunds_once(self):
        p=place_prediction(user=self.user,match_id=self.match.pk,outcome='draw',stake=Decimal('25'))
        self.match.status=Match.Status.POSTPONED; self.match.save()
        self.assertEqual(void_match(self.match.pk),1); self.assertEqual(void_match(self.match.pk),0)
        self.user.wallet.refresh_from_db(); p.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('1000.00')); self.assertEqual(p.status,Prediction.Status.VOID)

    def test_private_pages_require_auth_and_wallet_is_user_scoped(self):
        self.assertRedirects(self.client.get(reverse('dashboard')),f"{reverse('login')}?next={reverse('dashboard')}")
        self.client.force_login(self.user)
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'rival')

    def test_leaderboard_requires_three_settled_predictions(self):
        response=self.client.get(reverse('leaderboard'))
        self.assertNotContains(response,'player</td>')
        for index in range(3):
            match=self.match if index == 0 else Match.objects.create(competition=self.comp,home_team=self.home,away_team=self.away,kickoff=timezone.now()+timedelta(days=index+2))
            Prediction.objects.create(user=self.user,match=match,outcome='home',stake=Decimal('1'),multiplier=Decimal('2.00'),status=Prediction.Status.WON if index < 2 else Prediction.Status.LOST)
        response=self.client.get(reverse('leaderboard'))
        self.assertContains(response,'player</td>')
        self.assertContains(response,'67%')

class MultiSportTests(TestCase):
    def setUp(self):
        self.client=Client()
        self.user=User.objects.create_user('multi',password='Strongpass123!')
        self.rival=User.objects.create_user('othermulti',password='Strongpass123!')
        self.competition=Competition.objects.create(name='DEMO Soccer Cup',country='DEMO')
        self.team_a=Team.objects.create(name='DEMO Reds',short_name='RED',country='DEMO')
        self.team_b=Team.objects.create(name='DEMO Blues',short_name='BLU',country='DEMO')
        self.match=Match.objects.create(competition=self.competition,home_team=self.team_a,away_team=self.team_b,kickoff=timezone.now()+timedelta(days=2))
        self.constructor_a=Constructor.objects.create(name='DEMO North Racing',nationality='DEMO',color='#cc3344')
        self.constructor_b=Constructor.objects.create(name='DEMO South Racing',nationality='DEMO',color='#3366cc')
        self.drivers=[]
        for index in range(4):
            team=self.constructor_a if index < 2 else self.constructor_b
            self.drivers.append(Driver.objects.create(name=f'DEMO Driver {index+1}',abbreviation=f'D{index+1}X',number=70+index,nationality='DEMO',constructor=team))
        self.circuit=Circuit.objects.create(name='DEMO Test Circuit',locality='Sample City',country='DEMO',time_zone='UTC',length_km='4.500')
        self.gp=GrandPrix.objects.create(name='DEMO Sample Grand Prix',season=timezone.localdate().year,round_number=97,circuit=self.circuit,demo=True)
        self.gp.drivers.add(*self.drivers)
        now=timezone.now()
        self.race=Session.objects.create(grand_prix=self.gp,session_type=Session.Type.GRAND_PRIX,start_time=now+timedelta(days=1))
        self.qualifying=Session.objects.create(grand_prix=self.gp,session_type=Session.Type.QUALIFYING,start_time=now+timedelta(hours=12))

    def test_soccer_listing_and_market_predictions(self):
        self.assertEqual(self.client.get('/soccer/').status_code,200)
        self.assertContains(self.client.get('/soccer/matches/'),'DEMO Reds')
        home=place_prediction(user=self.user,match_id=self.match.pk,market=Prediction.Market.MATCH_RESULT,outcome=Prediction.Outcome.HOME,stake=Decimal('10'))
        btts=place_prediction(user=self.user,match_id=self.match.pk,market=Prediction.Market.BOTH_TEAMS_SCORE,outcome=Prediction.Outcome.YES,stake=Decimal('10'))
        goals=place_prediction(user=self.user,match_id=self.match.pk,market=Prediction.Market.TOTAL_GOALS,outcome=Prediction.Outcome.OVER_25,stake=Decimal('10'))
        self.match.home_score=2; self.match.away_score=1; self.match.status=Match.Status.COMPLETED; self.match.save()
        self.assertEqual(settle_match(self.match.pk),3)
        home.refresh_from_db(); btts.refresh_from_db(); goals.refresh_from_db()
        self.assertEqual(home.status,Prediction.Status.WON)
        self.assertEqual(btts.status,Prediction.Status.WON)
        self.assertEqual(goals.status,Prediction.Status.WON)

    def test_f1_calendar_and_race_detail_render(self):
        self.assertEqual(self.client.get('/f1/calendar/').status_code,200)
        self.assertEqual(self.client.get(f'/f1/race/{self.gp.pk}/').status_code,200)

    def test_f1_race_form_creates_prediction_and_duplicate_is_friendly(self):
        self.client.force_login(self.user)
        data={'session':self.race.pk,'market':F1Prediction.Market.RACE_WINNER,'driver':self.drivers[0].pk,'stake':'10'}
        response=self.client.post(f'/f1/race/{self.gp.pk}/',data)
        self.assertRedirects(response,f'/f1/race/{self.gp.pk}/')
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('990.00'))
        response=self.client.post(f'/f1/race/{self.gp.pk}/',data)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'already predicted this market')

    def test_f1_driver_and_constructor_standings_calculated_from_results(self):
        self.race.status=Session.Status.COMPLETED; self.race.save()
        for position, driver in enumerate(self.drivers,1):
            RaceResult.objects.create(session=self.race,driver=driver,constructor=driver.constructor,position=position,points=[25,18,15,12][position-1])
        response=self.client.get('/f1/standings/')
        self.assertContains(response,'DEMO Driver 1')
        self.assertContains(response,'DEMO North Racing')
        self.assertContains(response,'<td>25</td>',html=True)

    def test_f1_prediction_shares_wallet_and_race_settlement_is_idempotent(self):
        place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=self.drivers[0].pk,stake=Decimal('20'))
        place_f1_prediction(user=self.rival,session_id=self.race.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=self.drivers[1].pk,stake=Decimal('20'))
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('980.00'))
        soccer=place_prediction(user=self.user,match_id=self.match.pk,outcome=Prediction.Outcome.DRAW,stake=Decimal('5'))
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('975.00'))
        for position,driver in enumerate(self.drivers,1):
            RaceResult.objects.create(session=self.race,driver=driver,constructor=driver.constructor,position=position,points=[25,18,15,12][position-1],fastest_lap=position==4)
        self.race.status=Session.Status.COMPLETED; self.race.save()
        self.assertEqual(settle_f1_session(self.race.pk),2)
        self.assertEqual(settle_f1_session(self.race.pk),0)
        self.user.wallet.refresh_from_db()
        soccer.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('1045.00'))
        self.assertEqual(soccer.status,Prediction.Status.PENDING)

    def test_f1_podium_pole_and_fastest_lap_markets(self):
        picks = [
            place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.PODIUM,driver_id=self.drivers[1].pk,stake=Decimal('1')),
            place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.FASTEST_LAP,driver_id=self.drivers[3].pk,stake=Decimal('1')),
            place_f1_prediction(user=self.user,session_id=self.qualifying.pk,market=F1Prediction.Market.POLE,driver_id=self.drivers[0].pk,stake=Decimal('1')),
        ]
        for position,driver in enumerate(self.drivers,1):
            RaceResult.objects.create(session=self.race,driver=driver,constructor=driver.constructor,position=position,points=[25,18,15,12][position-1],fastest_lap=position==4)
            RaceResult.objects.create(session=self.qualifying,driver=driver,constructor=driver.constructor,position=position,points=0)
        self.race.status=Session.Status.COMPLETED; self.race.save()
        self.qualifying.status=Session.Status.COMPLETED; self.qualifying.save()
        self.assertEqual(settle_f1_session(self.race.pk),2)
        self.assertEqual(settle_f1_session(self.qualifying.pk),1)
        for pick in picks:
            pick.refresh_from_db()
            self.assertEqual(pick.status,F1Prediction.Status.WON)

    def test_f1_predictions_reject_started_session_invalid_driver_and_insufficient_balance(self):
        with self.assertRaisesMessage(ValueError,'active driver entered'):
            outsider=Driver.objects.create(name='DEMO Guest',abbreviation='GST',number=99,nationality='DEMO',constructor=self.constructor_a)
            place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=outsider.pk,stake=Decimal('1'))
        self.user.wallet.balance=Decimal('5'); self.user.wallet.save(update_fields=['balance'])
        with self.assertRaisesMessage(ValueError,'enough virtual credits'):
            place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.PODIUM,driver_id=self.drivers[0].pk,stake=Decimal('6'))
        self.race.start_time=timezone.now()-timedelta(seconds=1); self.race.save()
        with self.assertRaisesMessage(ValueError,'session starts'):
            place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=self.drivers[0].pk,stake=Decimal('1'))

    def test_f1_duplicate_prediction_and_wrong_session_market_rejected(self):
        place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=self.drivers[0].pk,stake=Decimal('1'))
        with self.assertRaises(IntegrityError):
            place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=self.drivers[1].pk,stake=Decimal('1'))
        with self.assertRaisesMessage(ValueError,'not available'):
            place_f1_prediction(user=self.user,session_id=self.qualifying.pk,market=F1Prediction.Market.RACE_WINNER,driver_id=self.drivers[0].pk,stake=Decimal('1'))

    def test_f1_partial_results_do_not_settle_and_cancel_refunds_once(self):
        prediction=place_f1_prediction(user=self.user,session_id=self.race.pk,market=F1Prediction.Market.PODIUM,driver_id=self.drivers[0].pk,stake=Decimal('12'))
        RaceResult.objects.create(session=self.race,driver=self.drivers[0],constructor=self.drivers[0].constructor,position=1,points=25)
        self.race.status=Session.Status.COMPLETED; self.race.save()
        self.assertEqual(settle_f1_session(self.race.pk),0)
        prediction.refresh_from_db(); self.assertEqual(prediction.status,F1Prediction.Status.PENDING)
        self.race.status=Session.Status.CANCELLED; self.race.save()
        self.assertEqual(void_f1_session(self.race.pk),1)
        self.assertEqual(void_f1_session(self.race.pk),0)
        self.user.wallet.refresh_from_db(); prediction.refresh_from_db()
        self.assertEqual(self.user.wallet.balance,Decimal('1000.00'))
        self.assertEqual(prediction.status,F1Prediction.Status.VOID)

    def test_demo_commands_are_idempotent(self):
        from io import StringIO
        call_command('load_soccer_demo_data',stdout=StringIO())
        soccer_counts=(Competition.objects.count(),Team.objects.count(),Match.objects.count())
        call_command('load_soccer_demo_data',stdout=StringIO())
        self.assertEqual(soccer_counts,(Competition.objects.count(),Team.objects.count(),Match.objects.count()))
        call_command('load_f1_demo_data',stdout=StringIO())
        f1_counts=(Constructor.objects.count(),Driver.objects.count(),Circuit.objects.count(),GrandPrix.objects.count(),Session.objects.count())
        call_command('load_f1_demo_data',stdout=StringIO())
        self.assertEqual(f1_counts,(Constructor.objects.count(),Driver.objects.count(),Circuit.objects.count(),GrandPrix.objects.count(),Session.objects.count()))
