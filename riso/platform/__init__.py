"""The technical base: settings, the database and its migrations, the unit of work, and
(from P2-M0-T04) file storage and the mail outbox. Domain packages never import it."""

from riso.platform.db import Base, Database, create_db_engine, metadata
from riso.platform.settings import Settings
from riso.platform.uow import SqlUnitOfWork

__all__ = ["Base", "Database", "Settings", "SqlUnitOfWork", "create_db_engine", "metadata"]
