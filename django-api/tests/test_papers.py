import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from papers.models import Paper, AnalysisJob


# ── FIXTURES ──────────────────────────────────────────────────────────────────
# Fixtures are reusable setup functions — pytest injects them automatically
# into any test function that declares them as parameters

@pytest.fixture
def api_client():
    """A plain API client with no authentication."""
    return APIClient()


@pytest.fixture
def test_user(db):
    """Creates a test user in the database."""
    return User.objects.create_user(
        username='testuser',
        password='testpass123'
    )


@pytest.fixture
def auth_client(test_user):
    """An API client pre-authenticated as test_user."""
    client = APIClient()
    refresh = RefreshToken.for_user(test_user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client


@pytest.fixture
def test_paper(test_user, db):
    """A paper owned by test_user."""
    return Paper.objects.create(
        url='https://arxiv.org/abs/1706.03762',
        title='Attention Is All You Need',
        submitted_by=test_user,
        status='pending'
    )


# ── TEST 1 — Unauthenticated request rejected ──────────────────────────────────
class TestAuthentication:

    def test_unauthenticated_request_rejected(self, api_client):
        """
        Any request without a JWT token must return 401.
        Verifies IsAuthenticated permission is enforced globally.
        """
        response = api_client.get('/api/papers/')
        assert response.status_code == 401
        assert 'credentials were not provided' in response.data['detail']

    def test_authenticated_request_allowed(self, auth_client):
        """
        A request with a valid JWT token must return 200.
        """
        response = auth_client.get('/api/papers/')
        assert response.status_code == 200

    def test_invalid_token_rejected(self, api_client):
        """
        A request with a malformed token must return 401.
        """
        api_client.credentials(HTTP_AUTHORIZATION='Bearer invalidtoken123')
        response = api_client.get('/api/papers/')
        assert response.status_code == 401


# ── TEST 2 — Paper creation ────────────────────────────────────────────────────
class TestPaperCreate:

    def test_paper_create_sets_submitted_by(self, auth_client, test_user, db):
        """
        When a paper is created, submitted_by must be
        set to the logged-in user automatically.
        Client never sends submitted_by — server injects it.
        """
        response = auth_client.post('/api/papers/', {
            'url': 'https://arxiv.org/abs/1234.5678',
            'title': 'Test Paper'
        }, format='json')

        assert response.status_code == 201
        assert response.data['submitted_by'] == 'testuser'

        # Verify in DB directly
        paper = Paper.objects.get(id=response.data['id'])
        assert paper.submitted_by == test_user

    def test_paper_create_requires_url(self, auth_client, db):
        """
        URL is a required field — missing it must return 400.
        """
        response = auth_client.post('/api/papers/', {
            'title': 'No URL Paper'
        }, format='json')

        assert response.status_code == 400
        assert 'url' in response.data

    def test_paper_create_invalid_url_rejected(self, auth_client, db):
        """
        A non-URL string must be rejected by URLField validation.
        """
        response = auth_client.post('/api/papers/', {
            'url': 'not-a-valid-url',
            'title': 'Bad URL Paper'
        }, format='json')

        assert response.status_code == 400
        assert 'url' in response.data

    def test_user_cannot_see_other_users_papers(self, auth_client, db):
        """
        A user must only see their own papers.
        Papers from other users must not appear in the list.
        """
        # Create another user with their own paper
        other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123'
        )
        Paper.objects.create(
            url='https://arxiv.org/abs/9999.9999',
            title='Other User Paper',
            submitted_by=other_user
        )

        # auth_client is logged in as test_user
        response = auth_client.get('/api/papers/')
        assert response.status_code == 200

        # test_user has no papers — list must be empty
        assert response.data['count'] == 0


# ── TEST 3 — Analyze action ────────────────────────────────────────────────────
class TestAnalyzeAction:

    def test_analyze_returns_job_id_immediately(self, auth_client, test_paper, db):
        """
        POST /api/papers/<id>/analyze/ must return a job_id instantly.
        Must NOT wait for processing to complete.
        Response status must be 202 Accepted (not 200 OK).
        202 means: request accepted, processing happening asynchronously.
        """
        response = auth_client.post(
            f'/api/papers/{test_paper.id}/analyze/'
        )

        assert response.status_code == 202
        assert 'job_id' in response.data
        assert response.data['status'] == 'pending'

        # Verify job was created in DB
        job_id = response.data['job_id']
        job = AnalysisJob.objects.get(id=job_id)
        assert job.status == 'pending'
        assert job.paper == test_paper

    def test_analyze_caches_job_status_in_redis(self, auth_client, test_paper, db):
        """
        After triggering analyze, job status must be in Redis.
        GET /api/jobs/<id>/status must return source: cache.
        Verifies the Redis-first pattern is working.
        """
        # Trigger analysis
        analyze_response = auth_client.post(
            f'/api/papers/{test_paper.id}/analyze/'
        )
        job_id = analyze_response.data['job_id']

        # Check Redis directly
        cached = cache.get(f'job:{job_id}:status')
        assert cached == 'pending'

        # Check status endpoint returns from cache
        status_response = auth_client.get(f'/api/jobs/{job_id}/status/')
        assert status_response.status_code == 200
        assert status_response.data['source'] == 'cache'

    def test_analyze_updates_paper_status(self, auth_client, test_paper, db):
        """
        After triggering analyze, the paper's status
        must update from 'pending' to 'processing'.
        """
        auth_client.post(f'/api/papers/{test_paper.id}/analyze/')

        # Refresh from DB
        test_paper.refresh_from_db()
        assert test_paper.status == 'processing'


# ── TEST 4 — JWT Auth endpoints ────────────────────────────────────────────────
class TestJWTAuth:

    def test_register_creates_user_and_returns_tokens(self, api_client, db):
        """
        POST /api/auth/register/ must create a user
        and return both access and refresh tokens.
        """
        response = api_client.post('/api/auth/register/', {
            'username': 'newuser',
            'email': 'new@test.com',
            'password': 'newpass123',
            'password2': 'newpass123'
        }, format='json')

        assert response.status_code == 201
        assert 'tokens' in response.data
        assert 'access' in response.data['tokens']
        assert 'refresh' in response.data['tokens']
        assert User.objects.filter(username='newuser').exists()

    def test_register_password_mismatch_rejected(self, api_client, db):
        """
        Mismatched passwords must return 400.
        """
        response = api_client.post('/api/auth/register/', {
            'username': 'newuser',
            'password': 'pass1234',
            'password2': 'differentpass'
        }, format='json')

        assert response.status_code == 400

    def test_login_returns_tokens(self, api_client, test_user, db):
        """
        POST /api/auth/login/ with valid credentials
        must return access and refresh tokens.
        """
        response = api_client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'testpass123'
        }, format='json')

        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login_wrong_password_rejected(self, api_client, test_user, db):
        """
        Wrong password must return 401.
        """
        response = api_client.post('/api/auth/login/', {
            'username': 'testuser',
            'password': 'wrongpassword'
        }, format='json')

        assert response.status_code == 401