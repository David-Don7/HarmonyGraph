"""Cover passage lookups and maintain statistics during incremental growth."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    # Transactional replacement: reads remain available while index creation
    # temporarily waits for/blocks writers. Failure rolls back to the old index.
    op.create_index(
        "ix_pattern_lookup_cover",
        "pattern_indexes",
        ["analysis_id", "mode", "token", "song_id", "position"],
        postgresql_include=["section_id"],
    )
    op.drop_index("ix_pattern_lookup", table_name="pattern_indexes")
    op.execute("ALTER INDEX ix_pattern_lookup_cover RENAME TO ix_pattern_lookup")
    # Most raw records never change, so the default table-wide threshold leaves
    # the small resolved subset badly underestimated for hours during rollout.
    op.execute(
        "ALTER TABLE catalog_records SET (autovacuum_analyze_scale_factor=0.002, autovacuum_analyze_threshold=250)"
    )
    op.execute(
        "ALTER TABLE catalog_artifacts SET (autovacuum_analyze_scale_factor=0.02, autovacuum_analyze_threshold=100)"
    )
    op.execute("ANALYZE catalog_records")
    op.execute("ANALYZE catalog_artifacts")
    op.execute("ANALYZE pattern_indexes")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index("ix_pattern_lookup", table_name="pattern_indexes")
    op.create_index("ix_pattern_lookup", "pattern_indexes", ["analysis_id", "mode", "token", "song_id", "position"])
    op.execute("ALTER TABLE catalog_records RESET (autovacuum_analyze_scale_factor, autovacuum_analyze_threshold)")
    op.execute("ALTER TABLE catalog_artifacts RESET (autovacuum_analyze_scale_factor, autovacuum_analyze_threshold)")
