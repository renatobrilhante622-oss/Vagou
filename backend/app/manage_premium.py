"""Operator-only plan management. No client-controlled grant endpoint exists."""
import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.models import User


async def set_premium(email: str, enabled: bool) -> str:
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as db:
            user = await db.scalar(select(User).where(User.email == email.strip().casefold()).with_for_update())
            if user is None or user.role != 'candidate':
                raise ValueError('Conta de candidato não encontrada.')
            user.is_premium = enabled
            if not enabled:
                user.automation_enabled = False
            return str(user.id)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description='Gerenciar o plano de uma conta pelo servidor autorizado.')
    parser.add_argument('--email', required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--grant', action='store_true')
    operation.add_argument('--revoke', action='store_true')
    arguments = parser.parse_args()
    try:
        user_id = asyncio.run(set_premium(arguments.email, arguments.grant))
    except ValueError as error:
        parser.error(str(error))
    print(f'Plano atualizado para a conta {user_id}. Consentimento e confirmação de e-mail continuam obrigatórios.')


if __name__ == '__main__':
    main()
