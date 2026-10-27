from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from football.models import Match
from .models import Prediction, Transaction, Wallet

MULTIPLIERS = {
    Prediction.Market.MATCH_RESULT: {Prediction.Outcome.HOME: Decimal('2.00'), Prediction.Outcome.DRAW: Decimal('3.20'), Prediction.Outcome.AWAY: Decimal('2.40')},
    Prediction.Market.BOTH_TEAMS_SCORE: {Prediction.Outcome.YES: Decimal('1.90'), Prediction.Outcome.NO: Decimal('1.90')},
    Prediction.Market.TOTAL_GOALS: {Prediction.Outcome.OVER_25: Decimal('1.95'), Prediction.Outcome.UNDER_25: Decimal('1.95')},
}

@transaction.atomic
def commit_stake(*, user, stake, description):
    """Debit a user's shared virtual wallet and record the auditable stake."""
    wallet = Wallet.objects.select_for_update().get(user=user)
    if wallet.balance < stake:
        raise ValueError('You do not have enough virtual credits.')
    before = wallet.balance
    wallet.balance -= stake
    wallet.save(update_fields=['balance', 'updated_at'])
    Transaction.objects.create(wallet=wallet, type=Transaction.Type.STAKE, amount=-stake, balance_before=before, balance_after=wallet.balance, description=description)
    return wallet

@transaction.atomic
def credit_wallet(*, user, amount, transaction_type, description):
    """Credit a user's shared wallet once the caller has verified the outcome."""
    wallet = Wallet.objects.select_for_update().get(user=user)
    before = wallet.balance
    wallet.balance += amount
    wallet.save(update_fields=['balance', 'updated_at'])
    Transaction.objects.create(wallet=wallet, type=transaction_type, amount=amount, balance_before=before, balance_after=wallet.balance, description=description)
    return wallet

@transaction.atomic
def place_prediction(*, user, match_id, outcome, stake, market=Prediction.Market.MATCH_RESULT):
    match = Match.objects.select_for_update().get(pk=match_id)
    if match.status != Match.Status.SCHEDULED or match.kickoff <= timezone.now():
        raise ValueError('Predictions are available only before kickoff for scheduled matches.')
    if market not in MULTIPLIERS or outcome not in MULTIPLIERS[market]:
        raise ValueError('Choose a valid selection for this prediction market.')
    if stake <= 0:
        raise ValueError('Stake must be greater than zero.')
    commit_stake(user=user, stake=stake, description=f'{match} ({market}): {stake} credits committed')
    prediction = Prediction.objects.create(user=user, match=match, market=market, outcome=outcome, stake=stake, multiplier=MULTIPLIERS[market][outcome])
    return prediction

@transaction.atomic
def settle_match(match_id):
    match = Match.objects.select_for_update().get(pk=match_id)
    if match.status != Match.Status.COMPLETED or match.home_score is None or match.away_score is None:
        return 0
    result = Prediction.Outcome.HOME if match.home_score > match.away_score else Prediction.Outcome.AWAY if match.away_score > match.home_score else Prediction.Outcome.DRAW
    total_goals = match.home_score + match.away_score
    count = 0
    for prediction in Prediction.objects.select_for_update().filter(match=match, status=Prediction.Status.PENDING).select_related('user'):
        wins = {
            Prediction.Market.MATCH_RESULT: prediction.outcome == result,
            Prediction.Market.BOTH_TEAMS_SCORE: prediction.outcome == (Prediction.Outcome.YES if match.home_score > 0 and match.away_score > 0 else Prediction.Outcome.NO),
            Prediction.Market.TOTAL_GOALS: prediction.outcome == (Prediction.Outcome.OVER_25 if total_goals >= 3 else Prediction.Outcome.UNDER_25),
        }[prediction.market]
        if wins:
            returned = (prediction.stake * prediction.multiplier).quantize(Decimal('0.01'))
            credit_wallet(user=prediction.user, amount=returned, transaction_type=Transaction.Type.WIN, description=f'Winning prediction: {match}')
            prediction.status = Prediction.Status.WON
            prediction.profit_loss = returned - prediction.stake
        else:
            prediction.status = Prediction.Status.LOST
            prediction.profit_loss = -prediction.stake
        prediction.settled_at = timezone.now()
        prediction.save(update_fields=['status', 'profit_loss', 'settled_at'])
        count += 1
    return count

@transaction.atomic
def void_match(match_id):
    match = Match.objects.select_for_update().get(pk=match_id)
    if match.status not in (Match.Status.POSTPONED, Match.Status.CANCELLED):
        return 0
    count = 0
    for prediction in Prediction.objects.select_for_update().filter(match=match, status=Prediction.Status.PENDING):
        credit_wallet(user=prediction.user, amount=prediction.stake, transaction_type=Transaction.Type.REFUND, description=f'Voided prediction: {match}')
        prediction.status = Prediction.Status.VOID
        prediction.profit_loss = Decimal('0')
        prediction.settled_at = timezone.now()
        prediction.save(update_fields=['status', 'profit_loss', 'settled_at'])
        count += 1
    return count
