from pathlib import Path

import pytest

from netops_agent.client import FixtureTransport, MerakiClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client() -> MerakiClient:
    return MerakiClient(api_key="test", transport=FixtureTransport(FIXTURES))
