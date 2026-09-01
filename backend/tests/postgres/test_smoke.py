from sqlalchemy import text
from sqlalchemy.orm import Session


def test_postgres_connection_reports_version(postgres_session: Session):
    version = postgres_session.execute(text("select version()")).scalar_one()

    assert "PostgreSQL" in version
