from django.core.management.base import BaseCommand, CommandError

from football.providers import SportsProviderError, sync_soccer_data


class Command(BaseCommand):
    help = 'Synchronize real Soccer competitions and fixtures from API-Football.'

    def add_arguments(self, parser):
        parser.add_argument('--players', action='store_true', help='Also synchronize provider squads (uses additional API quota).')

    def handle(self, *args, **options):
        try:
            counts = sync_soccer_data(include_players=options['players'])
        except SportsProviderError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS('API-Football synchronization complete: ' + ', '.join(f'{key}={value}' for key, value in counts.items())))
