import json
from io import BytesIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Competition, Match, Source, Team
from .providers import APIFootballClient, ProviderNotConfigured


class APIFootballProviderTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_missing_key_fails_without_network_request(self):
        with patch.dict('os.environ', {'SOCCER_API_KEY': '', 'SOCCER_DATA_API_KEY': ''}):
            with self.assertRaises(ProviderNotConfigured):
                APIFootballClient(api_key='').get('fixtures')

    def test_provider_call_is_authenticated_and_cached(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps({'response': [{'fixture': {'id': 123}}]}).encode()
        with patch('football.providers.urlopen', return_value=Response()) as urlopen:
            client = APIFootballClient(api_key='test-only', timeout=1)
            self.assertEqual(client.get('fixtures', {'id': 123}), [{'fixture': {'id': 123}}])
            self.assertEqual(client.get('fixtures', {'id': 123}), [{'fixture': {'id': 123}}])
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header('X-apisports-key'), 'test-only')

    def test_fixture_mapping_persists_provider_rows(self):
        from .providers import _save_fixture
        row = {
            'fixture': {'id': 771, 'date': '2026-10-28T18:00:00+00:00', 'status': {'short': 'NS'}, 'venue': {'name': 'Test Ground'}},
            'league': {'id': 39, 'name': 'Test League', 'season': 2026, 'round': 'Regular Season - 1'},
            'teams': {'home': {'id': 1, 'name': 'North', 'code': 'NOR', 'country': 'Test'}, 'away': {'id': 2, 'name': 'South', 'code': 'SOU', 'country': 'Test'}},
            'goals': {'home': None, 'away': None},
        }
        match = _save_fixture(row)
        self.assertEqual(match.source, Source.API_FOOTBALL)
        self.assertEqual(match.provider_id, '771')
        self.assertEqual(match.home_team.name, 'North')
        self.assertEqual(match.status, Match.Status.SCHEDULED)
        self.assertEqual(Match.objects.count(), 1)

    def test_sync_command_reports_missing_credentials_cleanly(self):
        with patch('football.management.commands.sync_soccer_data.sync_soccer_data', side_effect=ProviderNotConfigured('Set a provider key.')):
            with self.assertRaises(CommandError):
                call_command('sync_soccer_data')
