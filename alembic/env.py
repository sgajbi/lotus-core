# alembic/env.py
import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

# --- CUSTOM SETUP ---
# Add the project root directory to the Python path.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# Add the new src directory to the path
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)
# Update the path to portfolio-common inside src
portfolio_common_path = os.path.join(project_root, 'src', 'libs', 'portfolio-common')
if portfolio_common_path not in sys.path:
    sys.path.insert(0, portfolio_common_path)

# Load environment variables from the .env file at the project root
dotenv_path = os.path.join(project_root, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
# --- END CUSTOM SETUP ---

# this is the Alembic Config object
config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

# Import the models module so SQLAlchemy model classes register with Base.metadata for Alembic.
from portfolio_common import database_models

target_metadata = database_models.Base.metadata


def get_db_url():
    """
    Gets the correct DB URL for Alembic.
    Alembic runs synchronously, so it must use a synchronous driver scheme.
    """
    url = os.environ.get("HOST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if url is None:
        raise Exception(
            "Neither HOST_DATABASE_URL nor DATABASE_URL are set. "
            "Please check your .env file."
        )

    # Ensure the URL uses a synchronous scheme for alembic
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")

    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    engine_config = config.get_section(config.config_ini_section)
    engine_config["sqlalchemy.url"] = get_db_url()

    connectable = engine_from_config(
        engine_config,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
