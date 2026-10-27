import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from .providers import OpenF1Client, OpenF1NotConfigured


class OpenF1ProviderTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_historical_get_is_public_and_cached(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps([{'meeting_key': 42}]).encode()
        with patch('formula1.providers.urlopen', return_value=Response()) as urlopen:
            client = OpenF1Client(timeout=1)
            rows = client.get('meetings', {'year': 2025})
            self.assertEqual(rows, [{'meeting_key': 42}])
            self.assertEqual(client.get('meetings', {'year': 2025}), rows)
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertIsNone(request.get_header('Authorization'))

    @override_settings(OPENF1_USERNAME='', OPENF1_PASSWORD='')
    def test_live_status_requires_credentials(self):
        with patch('formula1.providers.urlopen') as urlopen:
            with self.assertRaises(OpenF1NotConfigured):
                OpenF1Client().get('race_control', {'session_key': 42}, authenticated=True)
        urlopen.assert_not_called()
