"""API registries never outlive a test, including clients without lifespan."""
import pytest
from api import session_store


@pytest.fixture(autouse=True)
def isolated_simulation_registry(monkeypatch):
    registry = session_store.SessionRegistry()
    monkeypatch.setattr(session_store, 'registry', registry)
    context = session_store.SimulationSession(registry.clock())
    with session_store.bind_session(context):
        yield
    registry.shutdown()
    context.close()
