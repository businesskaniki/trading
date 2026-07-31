from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User


class UserRepository:
    """
    Repository responsible for User database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> User:
        user = User(**kwargs)

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[User]:
        result = await self.db.execute(select(User).order_by(User.email))
        return result.scalars().all()

    async def update(self, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            setattr(user, key, value)

        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def delete(self, user: User) -> None:
        await self.db.delete(user)
        await self.db.commit()
