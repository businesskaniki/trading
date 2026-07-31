from uuid import UUID

from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.core.security import get_password_hash, verify_password


class UserService:
    """
    Business logic for users and authentication.
    """

    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def create_user(self, data: UserCreate):
        existing = await self.repository.get_by_email(data.email)
        if existing:
            raise ValueError("A user with this email already exists")

        return await self.repository.create(
            email=data.email,
            full_name=data.full_name,
            hashed_password=get_password_hash(data.password),
        )

    async def authenticate(self, email: str, password: str):
        user = await self.repository.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user(self, user_id: UUID):
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        return user

    async def get_user_by_email(self, email: str):
        return await self.repository.get_by_email(email)
