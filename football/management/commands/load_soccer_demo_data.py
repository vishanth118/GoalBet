from .load_demo_data import Command as BaseCommand

class Command(BaseCommand):
    help = 'Load idempotent, clearly labelled GoalBet soccer demonstration data.'
