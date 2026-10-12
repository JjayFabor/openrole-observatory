from sqlalchemy.ext.asyncio import AsyncSession

from app.quarantine.models import QuarantineRecord


class QuarantineRepository:
    """Persistence operations needed while isolating invalid source records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: QuarantineRecord) -> None:
        self._session.add(record)
        await self._session.flush()
