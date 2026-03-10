from portfolio_common.database_models import PositionTimeseries
from portfolio_common.timeseries_repository_base import TimeseriesRepositoryBase
from portfolio_common.utils import async_timed
from sqlalchemy import select


class TimeseriesRepository(TimeseriesRepositoryBase):
    @async_timed(repository="TimeseriesRepository", method="get_position_timeseries")
    async def get_position_timeseries(
        self, portfolio_id: str, security_id: str, a_date, epoch: int
    ) -> PositionTimeseries | None:
        stmt = select(PositionTimeseries).filter_by(
            portfolio_id=portfolio_id,
            security_id=security_id,
            date=a_date,
            epoch=epoch,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()
