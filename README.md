# GoalBet

GoalBet is a Django soccer and Formula 1 prediction website built around **virtual credits only**. It includes sports schedules and prediction history, a database-backed help centre, an optional AI support assistant, and private support tickets.

## Features

- Soccer and Formula 1 pages and prediction flows remain available.
- FAQ and error-code help content is stored in SQL and manageable through Django Admin.
- Floating assistant on normal pages answers from active FAQ/error records. When that context cannot answer, it stores a support ticket and returns its reference.
- Optional OpenAI Responses API explanations use only retrieved GoalBet help content. With no key, or when OpenAI is down, the local FAQ/error answer remains available.
- Support tickets are stored in SQL. Ticket confirmations are restricted to the signed-in owner or the browser session that submitted the request.
- Optional MongoDB conversation and feedback writes. MongoDB downtime does not prevent support ticket creation or the main website from working.
- `/health/` reports application and SQL database availability without exposing connection information.
- Request logging records method, path, HTTP status, and duration; credentials and request bodies are not logged.
- Soccer provider synchronization uses API-Football; F1 calendar/history uses OpenF1.
- Responsive pages reuse the existing GoalBet styling. No payment, real-money wagering, or deposits are provided.

## Architecture

- Django apps: `core` (website, authentication, help and support), `football`, `formula1`, `predictions`, and `sports_ai`.
- SQLite is used locally. `DATABASE_URL` configures PostgreSQL in the included Render blueprint.
- FAQ, error codes, tickets, users, and predictions use the relational database.
- MongoDB is an optional document store for assistant chat/feedback logs only.
- OpenAI and sports APIs are server-side optional integrations. Secrets are never sent to the browser.

## Local setup (Windows / PowerShell)

From the folder containing `manage.py`:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_help_content
python manage.py createsuperuser
python manage.py check
python manage.py test
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. `db.sqlite3` is preserved; migrations add the new help/ticket tables without resetting accounts or sports records. If PowerShell blocks activation, use `py -3.13 -m pip install -r requirements.txt` and `py -3.13 manage.py ...` directly.

## Environment variables

Copy `.env.example` to `.env` for local development. All values there are placeholders. Never commit `.env` or put secrets in templates or JavaScript.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Private Django signing key. Required when `DJANGO_DEBUG=0`. |
| `DJANGO_DEBUG` | `1` locally; set `0` in production. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames. |
| `DATABASE_URL` | Optional PostgreSQL URL; otherwise local SQLite is used. |
| `OPENAI_API_KEY` | Optional server-side key for the assistant's database-grounded explanation. |
| `OPENAI_MODEL` | OpenAI Responses model ID; defaults to `gpt-6-astra`. |
| `MONGODB_URI`, `MONGODB_DATABASE` | Optional MongoDB connection and database for assistant logs/feedback. |
| `SOCCER_API_KEY`, `OPENF1_USERNAME`, `OPENF1_PASSWORD` | Optional sports-provider configuration used by the sports integration. |
| `SOCCER_API_TIMEOUT`, `F1_API_TIMEOUT` | Optional provider request timeout in seconds (default 8). |
| `DJANGO_SECURE_SSL_REDIRECT` | Keep `1` on HTTPS production hosting. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins for custom reverse-proxy/domain setups. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Optional SMTP settings for a future ticket-notification workflow. Production selects SMTP; local development uses console mail. |
| `ASSISTANT_RATE_LIMIT`, `TICKET_RATE_LIMIT` | Per-IP request limits per minute. |

### FAQ and error help

The first content is seeded idempotently:

```powershell
py -3.13 manage.py seed_help_content
```

Edit FAQ and error-code entries at `/admin/`. Do not put secrets or private user information into public FAQ entries.

### OpenAI assistant

Set `OPENAI_API_KEY` on the server to enable AI narration. The assistant retrieves FAQ/error content from SQL first and instructs the provider to answer only from that context. If the key is absent, the SDK is missing, or the provider fails, GoalBet uses the local database fallback. Provider failure does not stop support-ticket creation. The API key is never returned to the browser. OpenAI uses the Responses API: [official quickstart](https://developers.openai.com/api/docs/quickstart).

### MongoDB

MongoDB is optional. Set `MONGODB_URI` and `MONGODB_DATABASE` to a managed MongoDB connection. The app stores conversation identifiers, timestamps, bounded/redacted user and assistant text, FAQ/error references, ticket-created status, provider mode, and an optional pseudonymous user reference; feedback is stored separately. Do not include passwords, auth headers, session cookies, or API keys in chat. MongoDB connection/write failures are logged by exception type and do not block ticket saves. Without a URI, feedback reports that persistence is unavailable rather than pretending it was saved.

### Sports-data synchronization

Run provider syncs from the project folder (or schedule them as a host cron job):

```powershell
py -3.13 manage.py sync_soccer_data
py -3.13 manage.py sync_soccer_data --players
py -3.13 manage.py sync_f1_data --year 2025 --details
py -3.13 manage.py sync_f1_data --live
```

Soccer sync needs an API-Football API key and is subject to the account's provider quota. `--players` makes additional calls. OpenF1 offers historical endpoints from 2023 without login; `--live` requires OpenF1 subscription credentials. Failed syncs return a command error and do not invent fixtures/results. Data is stored in provider-source rows; existing demo rows remain marked as demo. See the [API-Football documentation](https://www.api-football.com/documentation-v3), [OpenF1 API documentation](https://openf1.org/docs/), and [OpenF1 authentication details](https://openf1.org/auth.html).

## Tests and operations

```powershell
py -3.13 manage.py check
py -3.13 manage.py makemigrations --check --dry-run
py -3.13 manage.py test
py -3.13 manage.py migrate --plan
py -3.13 manage.py migrate
py -3.13 manage.py seed_help_content
py -3.13 manage.py collectstatic --noinput
```

Tests mock external AI/MongoDB behavior and do not call paid services. `/health/` returns `200` when the SQL database is reachable and `503` without exposing database details otherwise. Log lines omit request bodies and headers.

## HTTPS deployment (Render example)

`render.yaml` provisions a web service and PostgreSQL database, runs migrations and static collection before deploy, serves static assets through WhiteNoise, and checks `/health/`. To deploy:

1. Create a private/public GitHub repository and push this project (never push `.env`, `db.sqlite3`, keys, or production data).
2. In Render, create a Blueprint from that repository and review its PostgreSQL/web service plan and costs before creating resources.
3. Set `OPENAI_API_KEY`, `MONGODB_URI`, `SOCCER_API_KEY`, and OpenF1 credentials in the Render service environment only if you have configured those services. Do not paste secrets into GitHub or this file.
4. Keep `DJANGO_DEBUG=0`, use the generated `DJANGO_SECRET_KEY`, configure `DJANGO_ALLOWED_HOSTS` for the actual assigned domain, and retain HTTPS redirect/cookie settings.
5. After deploy, open the actual Render-provided HTTPS URL, check `/health/`, test sign-up/login, FAQ, assistant fallback, and support-ticket confirmation. Review logs for errors without sharing secret values.
6. Back up production PostgreSQL and MongoDB under the providers' backup policies before future schema changes.

If the host does not run the blueprint's pre-deploy command, run `python manage.py migrate --noinput` and `python manage.py collectstatic --noinput` as its release command. HTTPS custom domains and database backups must be configured in the host dashboard.

**Live HTTPS website:** Not deployed yet; add the real host URL after deployment.  
**GitHub repository:** Not configured yet; add the real repository URL after creation.

## Known setup requirements / future work

- OpenAI narration, MongoDB log persistence, and authenticated/live sports-provider calls need valid service credentials. Local functionality does not require those credentials.
- Current request throttling uses Django's local-memory cache by default. Configure a shared cache such as Redis when running multiple production workers.
- Add a staff-facing ticket response/notification workflow and monitoring/alerting as a future improvement.
