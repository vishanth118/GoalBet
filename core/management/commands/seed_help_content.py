from django.core.management.base import BaseCommand
from core.models import ErrorCode, FAQ


FAQS = [
    ('What does GoalBet do?', 'GoalBet is a sports prediction and learning platform for soccer and Formula 1. It uses virtual credits only; it does not accept deposits or real-money bets.', 'Getting started'),
    ('How do soccer predictions work?', 'Choose an available match and market, select an outcome, and stake virtual credits before kickoff. Your prediction is settled when a verified match result is available.', 'Soccer'),
    ('How do Formula 1 predictions work?', 'Choose an available session, prediction market, and driver before that session starts. Virtual-credit predictions settle when session results are recorded.', 'Formula 1'),
    ('How should I interpret prediction confidence?', 'Any estimate is an aid to understanding historical data, not a guarantee. Small samples and changing conditions can make estimates uncertain.', 'Predictions'),
    ('Are predictions guaranteed?', 'No. Sports outcomes are uncertain. GoalBet predictions are for entertainment and learning and are never guaranteed.', 'Predictions'),
    ('How do I navigate GoalBet?', 'Use Soccer or Formula 1 in the navigation to browse events. Your dashboard, history, and leaderboard are available from the main navigation.', 'Getting started'),
    ('How do I contact support?', 'Use the Support page to submit a question. You can also ask the floating assistant; unresolved questions can be saved as support tickets.', 'Support'),
    ('How do I report a problem?', 'Describe what happened, include the page and any visible error code, and submit it from Support. Do not include your password or payment details.', 'Support'),
    ('How do support tickets work?', 'A ticket is saved in the GoalBet database and receives a unique reference. Staff can review and update it in the admin site.', 'Support'),
    ('How can I troubleshoot a website error?', 'Refresh once, check your connection, and visit Error-code help for the message you see. If the issue continues, send Support the error code and page name.', 'Troubleshooting'),
]

ERRORS = [
    ('400', 'Bad request', 'The request could not be understood.', 'A form may be incomplete or contain an invalid value.', 'Check required fields and try again.'),
    ('401', 'Sign in required', 'You need to sign in to access this page.', 'Your session may have expired.', 'Sign in again and repeat the action.'),
    ('403', 'Access denied', 'You do not have permission to perform this action.', 'The page may be restricted to another account or staff.', 'Return to your account and contact support if you think this is a mistake.'),
    ('404', 'Page not found', 'The requested page does not exist.', 'The link may be outdated or mistyped.', 'Check the address or return to the home page.'),
    ('429', 'Too many requests', 'GoalBet is receiving requests too quickly.', 'Repeated form submissions or assistant messages.', 'Wait briefly, then try again once.'),
    ('500', 'Server error', 'GoalBet encountered an unexpected problem.', 'A temporary application issue.', 'Try again later. If it continues, contact support with the time and page.'),
    ('503', 'Service unavailable', 'A required service is temporarily unavailable.', 'Database or optional provider downtime.', 'Wait briefly and try again; cached data may remain available.'),
    ('GB-001', 'GoalBet request could not be completed', 'GoalBet could not safely complete the requested action.', 'The request may no longer be available or required data is missing.', 'Refresh the page. If it continues, contact support and mention GB-001.'),
]


class Command(BaseCommand):
    help = 'Create or update the initial GoalBet FAQ and error-code reference content.'

    def handle(self, *args, **options):
        for question, answer, category in FAQS:
            FAQ.objects.update_or_create(question=question, defaults={'answer': answer, 'category': category, 'active': True})
        for code, title, explanation, causes, steps in ERRORS:
            ErrorCode.objects.update_or_create(code=code, defaults={'title': title, 'explanation': explanation, 'common_causes': causes, 'troubleshooting': steps, 'active': True})
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(FAQS)} FAQs and {len(ERRORS)} error explanations.'))
