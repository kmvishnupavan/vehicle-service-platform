"""
Pytest Test Fixtures and Test Client Setup.
"""

from datetime import datetime, timezone
from typing import AsyncGenerator
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.config import Settings, get_settings
from app.db.dependencies import get_current_user
from app.main import app
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole

CUSTOMER_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
MECHANIC_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def get_test_settings() -> Settings:
    """Return test settings with safe test credentials."""
    return Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test_key_placeholder",
        SUPABASE_SERVICE_ROLE_KEY="service_role_test_key_placeholder",
        SUPABASE_JWT_SECRET="test_jwt_secret_key_minimum_32_characters_long",
        CORS_ORIGINS=["http://localhost:3000"],
        RAZORPAY_KEY_ID="rzp_test_mock_key_id_12345",
        RAZORPAY_KEY_SECRET="mock_razorpay_secret_key_for_testing",
        RAZORPAY_WEBHOOK_SECRET="mock_razorpay_webhook_secret_for_testing",
    )


@pytest.fixture
def override_settings(monkeypatch):
    """Fixture providing test configuration override."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_mock_key_id_12345")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "mock_razorpay_secret_key_for_testing")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "mock_razorpay_webhook_secret_for_testing")
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = get_test_settings
    yield get_test_settings()
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def mock_customer():
    """Fixture providing an authenticated customer (Customer 1)."""
    user = AuthenticatedUser(
        id=CUSTOMER_1_ID,
        email="customer1@example.com",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_1_ID,
            full_name="Alice Customer",
            phone="+919876543210",
            email="customer1@example.com",
            avatar_url=None,
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_other_customer():
    """Fixture providing a different authenticated customer (Customer 2)."""
    user = AuthenticatedUser(
        id=CUSTOMER_2_ID,
        email="customer2@example.com",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_2_ID,
            full_name="Bob Customer",
            phone="+919876543211",
            email="customer2@example.com",
            avatar_url=None,
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_mechanic():
    """Fixture providing an authenticated mechanic."""
    user = AuthenticatedUser(
        id=MECHANIC_ID,
        email="mechanic1@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECHANIC_ID,
            full_name="Dave Mechanic",
            phone="+919876543220",
            email="mechanic1@example.com",
            avatar_url="https://example.com/avatars/dave.png",
            role=UserRole.MECHANIC,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


OTHER_MECHANIC_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def mock_other_mechanic():
    """Fixture providing a different authenticated mechanic."""
    user = AuthenticatedUser(
        id=OTHER_MECHANIC_ID,
        email="mechanic2@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=OTHER_MECHANIC_ID,
            full_name="Evan Mechanic",
            phone="+919876543221",
            email="mechanic2@example.com",
            avatar_url=None,
            role=UserRole.MECHANIC,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous HTTP test client fixture."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

