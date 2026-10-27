from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from formula1.providers import OpenF1Error, sync_f1_data


class Command(BaseCommand):
    help = 'Synchronize OpenF1 historical sessions; live access requires an OpenF1 subscription.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=timezone.localdate().year)
        parser.add_argument('--details', action='store_true', help='Load classification and telemetry for recent race sessions.')
        parser.add_argument('--live', action='store_true', help='Poll live status (requires paid OpenF1 credentials).')

    def handle(self, *args, **options):
        try:
            counts = sync_f1_data(year=options['year'], include_details=options['details'], include_live=options['live'])
        except OpenF1Error as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS('OpenF1 synchronization complete: ' + ', '.join(f'{key}={value}' for key, value in counts.items())))
