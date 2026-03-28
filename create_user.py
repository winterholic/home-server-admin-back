#!/usr/bin/env python3
"""
사용자 생성 CLI 스크립트
Shell에서 직접 SQL INSERT를 사용하면 bcrypt 해시의 $ 문자가
bash 변수로 해석되어 해시가 깨집니다. 이 스크립트를 사용하세요.

사용법:
  cd home-server-admin-back
  python create_user.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from getpass import getpass
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.user import User
from app.database import Base
from app.auth import get_password_hash


async def create_or_update_user(username: str, password: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        result = await db.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()

        hashed = get_password_hash(password)

        if existing:
            print(f"User '{username}' already exists.")
            answer = input("Update password? [y/N] ").strip().lower()
            if answer != "y":
                print("Cancelled.")
                await engine.dispose()
                return
            existing.hashed_password = hashed
            await db.commit()
            print(f"Password updated for '{username}'.")
        else:
            user = User(username=username, hashed_password=hashed, is_active=True)
            db.add(user)
            await db.commit()
            print(f"User '{username}' created successfully.")

    await engine.dispose()


if __name__ == "__main__":
    print("=== HomeServer Admin — User Setup ===")

    username = input("Username: ").strip()
    if not username:
        print("Error: username cannot be empty.")
        sys.exit(1)

    password = getpass("Password: ")
    if not password:
        print("Error: password cannot be empty.")
        sys.exit(1)

    confirm = getpass("Confirm password: ")
    if password != confirm:
        print("Error: passwords do not match.")
        sys.exit(1)

    asyncio.run(create_or_update_user(username, password))
