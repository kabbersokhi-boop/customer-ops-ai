from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return naive UTC for compatibility with current SQLAlchemy DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)
