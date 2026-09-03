"""Fast, DB-free test that the scheduler's job registry names exactly the
three jobs the rest of the system (Cloud Scheduler config, docs) expects."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.scheduler import JOB_REGISTRY


def test_job_registry_has_exactly_the_three_job_types():
    assert set(JOB_REGISTRY) == {"alert_check", "autosync", "dividend_notify"}
