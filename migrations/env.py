from alembic import context
from harmonygraph.db import Base, make_engine
from sqlalchemy import inspect, text


def run_migrations(connection):
    external_transaction = connection.in_transaction()
    # Early development builds used Alembic's default table, also used by Optuna.
    # Preserve that application revision while giving each system its own namespace.
    tables = set(inspect(connection).get_table_names())
    if (
        "alembic_version" in tables
        and "harmonygraph_schema_version" not in tables
        and {"songs", "analysis_runs"}.issubset(tables)
    ):
        versions = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        if versions == ["0001"]:
            connection.execute(text("ALTER TABLE alembic_version RENAME TO harmonygraph_schema_version"))
    if not external_transaction and connection.in_transaction():
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table="harmonygraph_schema_version",
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    import os

    context.configure(
        url=os.environ.get("DATABASE_URL", "sqlite:///data/local/harmonygraph-v1.db"),
        target_metadata=Base.metadata,
        version_table="harmonygraph_schema_version",
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        run_migrations(supplied)
    else:
        with make_engine().connect() as connection:
            run_migrations(connection)
