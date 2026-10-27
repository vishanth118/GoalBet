from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from formula1.models import RaceResult, Session
from predictions.models import F1Prediction, Transaction
from predictions.services import commit_stake, credit_wallet

REQUIRED_SESSION = {
    F1Prediction.Market.RACE_WINNER: Session.Type.GRAND_PRIX,
    F1Prediction.Market.PODIUM: Session.Type.GRAND_PRIX,
    F1Prediction.Market.FASTEST_LAP: Session.Type.GRAND_PRIX,
    F1Prediction.Market.POLE: Session.Type.QUALIFYING,
}

@transaction.atomic
def place_f1_prediction(*, user, session_id, market, driver_id, stake):
    session = Session.objects.select_for_update().select_related('grand_prix').get(pk=session_id)
    if session.status != Session.Status.SCHEDULED or session.start_time <= timezone.now():
        raise ValueError('Predictions close when a session starts.')
    if market not in REQUIRED_SESSION or session.session_type != REQUIRED_SESSION[market]:
        raise ValueError('That prediction market is not available for this session.')
    if stake <= 0:
        raise ValueError('Stake must be greater than zero.')
    from formula1.models import Driver
    driver = Driver.objects.filter(pk=driver_id, active=True, grand_prix_entries=session.grand_prix).first()
    if driver is None:
        raise ValueError('Choose an active driver entered for this Grand Prix.')
    multipliers = __import__('django.conf', fromlist=['settings']).settings.F1_SIMULATED_MULTIPLIERS
    if market not in multipliers:
        raise ValueError('This simulated market is not configured.')
    commit_stake(user=user, stake=stake, description=f'{session.grand_prix} {session.get_session_type_display()} ({market}): {stake} virtual credits committed')
    return F1Prediction.objects.create(user=user, session=session, market=market, selected_driver=driver, stake=stake, multiplier=Decimal(str(multipliers[market])))

def _winning_driver_ids(session, market):
    results = RaceResult.objects.filter(session=session)
    expected = set(session.grand_prix.drivers.filter(active=True).values_list('pk', flat=True))
    recorded = set(results.values_list('driver_id', flat=True))
    if not expected or not expected.issubset(recorded):
        return None
    if market == F1Prediction.Market.POLE:
        return set(results.filter(position=1, status=RaceResult.Status.FINISHED).values_list('driver_id', flat=True))
    if market == F1Prediction.Market.RACE_WINNER:
        return set(results.filter(position=1, status=RaceResult.Status.FINISHED).values_list('driver_id', flat=True))
    if market == F1Prediction.Market.PODIUM:
        # Do not settle from partial classifications.
        if results.filter(position__in=[1, 2, 3], status=RaceResult.Status.FINISHED).count() < 3:
            return None
        return set(results.filter(position__in=[1, 2, 3], status=RaceResult.Status.FINISHED).values_list('driver_id', flat=True))
    if market == F1Prediction.Market.FASTEST_LAP:
        return set(results.filter(fastest_lap=True, status=RaceResult.Status.FINISHED).values_list('driver_id', flat=True))
    return None

@transaction.atomic
def settle_f1_session(session_id):
    session = Session.objects.select_for_update().get(pk=session_id)
    if session.status != Session.Status.COMPLETED:
        return 0
    count = 0
    pending = F1Prediction.objects.select_for_update().filter(session=session, status=F1Prediction.Status.PENDING)
    for prediction in pending:
        winners = _winning_driver_ids(session, prediction.market)
        if not winners:
            continue
        if prediction.selected_driver_id in winners:
            returned = (prediction.stake * prediction.multiplier).quantize(Decimal('0.01'))
            credit_wallet(user=prediction.user, amount=returned, transaction_type=Transaction.Type.WIN, description=f'Winning F1 prediction: {session}')
            prediction.status = F1Prediction.Status.WON
            prediction.profit_loss = returned - prediction.stake
        else:
            prediction.status = F1Prediction.Status.LOST
            prediction.profit_loss = -prediction.stake
        prediction.settled_at = timezone.now()
        prediction.save(update_fields=['status', 'profit_loss', 'settled_at'])
        count += 1
    return count

@transaction.atomic
def void_f1_session(session_id):
    session = Session.objects.select_for_update().get(pk=session_id)
    if session.status != Session.Status.CANCELLED:
        return 0
    count = 0
    pending = F1Prediction.objects.select_for_update().filter(session=session, status=F1Prediction.Status.PENDING)
    for prediction in pending:
        credit_wallet(user=prediction.user, amount=prediction.stake, transaction_type=Transaction.Type.REFUND, description=f'F1 session void refund: {session}')
        prediction.status = F1Prediction.Status.VOID
        prediction.profit_loss = Decimal('0')
        prediction.settled_at = timezone.now()
        prediction.save(update_fields=['status', 'profit_loss', 'settled_at'])
        count += 1
    return count
