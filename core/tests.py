import json
import os
import subprocess
import sys
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.core.management import call_command
from django.core.cache import cache
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import ErrorCode, FAQ, SupportTicket


class HelpCentreTests(TestCase):
    def setUp(self):
        self.client = Client()
        cache.clear()
        call_command('seed_help_content', verbosity=0)

    def test_home_and_major_help_pages_render(self):
        for name in ('home', 'soccer_home', 'f1_home', 'faq', 'error_codes', 'support', 'health'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
        self.assertContains(self.client.get(reverse('home')), 'assistant-root')

    def test_faqs_are_served_from_database_and_seed_has_ten(self):
        self.assertGreaterEqual(FAQ.objects.filter(active=True).count(), 10)
        response = self.client.get(reverse('faq'))
        self.assertContains(response, 'What does GoalBet do?')
        FAQ.objects.filter(question='What does GoalBet do?').update(active=False)
        self.assertNotContains(self.client.get(reverse('faq')), 'What does GoalBet do?')

    def test_error_code_search_and_assistant_retrieval(self):
        response = self.client.get(reverse('error_codes'), {'q': 'GB-001'})
        self.assertContains(response, 'GB-001')
        response = self.client.post(reverse('assistant_chat'), data=json.dumps({'message': 'What does HTTP 404 mean?'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Page not found', response.json()['answer'])
        self.assertFalse(response.json()['ticket_reference'])

    def test_assistant_falls_back_without_api_key(self):
        with override_settings(OPENAI_API_KEY=''):
            with patch('openai.OpenAI') as client_factory:
                result = self.client.post(reverse('assistant_chat'), data=json.dumps({'message': 'How do soccer predictions work?'}), content_type='application/json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['mode'], 'database_fallback')
        self.assertIn('available match', result.json()['answer'].lower())
        client_factory.assert_not_called()

    def test_ai_provider_failure_uses_local_fallback_and_creates_ticket_if_unresolved(self):
        with override_settings(OPENAI_API_KEY='not-a-real-key'):
            with patch('core.assistant_service._ai_answer', return_value=None):
                response = self.client.post(reverse('assistant_chat'), data=json.dumps({'message': 'blorptwizzle ZXQ-493'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        reference = response.json()['ticket_reference']
        self.assertTrue(reference)
        ticket = SupportTicket.objects.get(reference=reference)
        self.assertEqual(ticket.question, 'blorptwizzle ZXQ-493')
        self.assertIn(reference, response.json()['answer'])

    def test_openai_timeout_uses_faq_fallback(self):
        with override_settings(OPENAI_API_KEY='configured-for-test'):
            with patch('openai.OpenAI', side_effect=TimeoutError('provider timed out')):
                response = self.client.post(reverse('assistant_chat'), data=json.dumps({'message': 'How do soccer predictions work?'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'database_fallback')
        self.assertIn('available match', response.json()['answer'].lower())

    def test_chat_log_failure_is_non_blocking_and_sensitive_text_is_redacted(self):
        from core.assistant_service import answer_question
        class Collection:
            document = None
            def insert_one(self, document):
                self.document = document
                raise RuntimeError('MongoDB offline')
        collection = Collection()
        request = RequestFactory().post('/assistant/chat/')
        request.user = AnonymousUser()
        with patch('core.assistant_service._mongo_collection', return_value=collection):
            result = answer_question('How do soccer predictions work? email me at person@example.test password=hunter2', request=request)
        self.assertIn('available match', result['answer'].lower())
        self.assertIn('[email redacted]', collection.document['user_message'])
        self.assertIn('password=[redacted]', collection.document['user_message'])

    def test_invalid_assistant_payload_and_rate_limit(self):
        self.assertEqual(self.client.post(reverse('assistant_chat'), data='not json', content_type='application/json').status_code, 400)
        cache.clear()
        with override_settings(ASSISTANT_RATE_LIMIT=1):
            first = self.client.post(reverse('assistant_chat'), data=json.dumps({'message': 'How do predictions work?'}), content_type='application/json')
            second = self.client.post(reverse('assistant_chat'), data=json.dumps({'message': 'How do predictions work?'}), content_type='application/json')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_support_ticket_creation_and_confirmation(self):
        response = self.client.post(reverse('submit_ticket'), {'email': 'visitor@example.test', 'subject': 'Question', 'question': 'I need help with my account', 'description': 'Details'})
        ticket = SupportTicket.objects.get()
        self.assertRedirects(response, reverse('ticket_confirmation', kwargs={'reference': ticket.reference}))
        self.assertContains(self.client.get(response.url), ticket.reference)
        self.assertIn('visitor@example.test', ticket.description)

    def test_ticket_validation_and_rate_limit(self):
        response = self.client.post(reverse('submit_ticket'), {'subject': '', 'question': 'short'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SupportTicket.objects.count(), 0)
        cache.clear()
        with override_settings(TICKET_RATE_LIMIT=1):
            data = {'email': 'visitor@example.test', 'subject': 'A question', 'question': 'Please help with this issue'}
            self.assertEqual(self.client.post(reverse('submit_ticket'), data).status_code, 302)
            self.assertEqual(self.client.post(reverse('submit_ticket'), data).status_code, 429)

    def test_ticket_confirmation_is_private(self):
        owner = get_user_model().objects.create_user(username='owner', password='Correct-pass-42!')
        other = get_user_model().objects.create_user(username='other', password='Correct-pass-42!')
        ticket = SupportTicket.objects.create(subject='Private', question='A private support issue', user=owner)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('ticket_confirmation', kwargs={'reference': ticket.reference})).status_code, 404)

    def test_feedback_does_not_break_when_mongodb_missing(self):
        with override_settings(MONGODB_URI=''):
            response = self.client.post(reverse('assistant_feedback'), data=json.dumps({'conversation_id': 'abc123', 'helpful': True}), content_type='application/json')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['saved'])

    def test_feedback_is_accepted_when_document_store_saves(self):
        with patch('core.views.save_feedback', return_value=True) as save:
            response = self.client.post(reverse('assistant_feedback'), data=json.dumps({'conversation_id': 'abc123', 'helpful': False}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['saved'])
        save.assert_called_once_with('abc123', False, '')

    def test_environment_rejects_placeholder_production_secret(self):
        environment = os.environ.copy()
        environment.update({'DJANGO_SETTINGS_MODULE': 'myproject.settings', 'DJANGO_DEBUG': '0', 'DJANGO_SECRET_KEY': 'replace-with-a-private-random-secret', 'DJANGO_ALLOWED_HOSTS': 'goalbet.example.test'})
        result = subprocess.run([sys.executable, '-c', 'import django; django.setup()'], cwd=os.path.dirname(os.path.dirname(__file__)), env=environment, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY must be set', result.stderr)

    def test_assistant_and_ticket_post_require_csrf(self):
        strict_client = Client(enforce_csrf_checks=True)
        chat = strict_client.post(reverse('assistant_chat'), data=json.dumps({'message': 'Question'}), content_type='application/json')
        ticket = strict_client.post(reverse('submit_ticket'), {'email': 'visitor@example.test', 'subject': 'Question', 'question': 'Please help me with this issue'})
        self.assertEqual(chat.status_code, 403)
        self.assertEqual(ticket.status_code, 403)

    @override_settings(DEBUG=False)
    def test_custom_404_response_has_assistant_action(self):
        response = self.client.get('/missing-help-page/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Ask the assistant', status_code=404)

    def test_health_reports_database_failure_without_details(self):
        class BrokenConnections:
            def __getitem__(self, alias):
                raise OperationalError('private connection detail')
        with patch('core.views.connections', BrokenConnections()):
            response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, 'private connection detail', status_code=503)

    def test_custom_500_view_uses_friendly_template(self):
        from core.error_views import server_error
        request = RequestFactory().get('/')
        request.user = AnonymousUser()
        response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'HTTP 500', response.content)

