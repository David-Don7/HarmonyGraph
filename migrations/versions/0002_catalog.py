"""Real catalog, provider cache and immutable publication watermarks."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "catalog_records",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("dataset_id", sa.String(), sa.ForeignKey("datasets.id"), primary_key=False, nullable=False),
        sa.Column("source_id", sa.String(), primary_key=False, nullable=False),
        sa.Column("raw", sa.JSON(), primary_key=False, nullable=False),
        sa.Column("track_id", sa.String(), primary_key=False, nullable=True),
        sa.Column("spotify_artist_id", sa.String(), primary_key=False, nullable=True),
        sa.Column("title", sa.String(), primary_key=False, nullable=True),
        sa.Column("artist", sa.String(), primary_key=False, nullable=True),
        sa.Column("artwork", sa.String(), primary_key=False, nullable=True),
        sa.Column("genre", sa.String(), primary_key=False, nullable=True),
        sa.Column("year", sa.Integer(), primary_key=False, nullable=True),
        sa.Column("date_precision", sa.String(), primary_key=False, nullable=True),
        sa.Column("metadata_status", sa.String(), primary_key=False, nullable=False),
        sa.Column("song_id", sa.String(), sa.ForeignKey("songs.id"), primary_key=False, nullable=True, unique=True),
        sa.Column("error", sa.Text(), primary_key=False, nullable=True),
        sa.UniqueConstraint("dataset_id", "source_id"),
    )
    op.create_index("ix_catalog_records_artist", "catalog_records", ["artist"])
    op.create_index("ix_catalog_records_dataset_id", "catalog_records", ["dataset_id"])
    op.create_index("ix_catalog_records_genre", "catalog_records", ["genre"])
    op.create_index("ix_catalog_records_metadata_status", "catalog_records", ["metadata_status"])
    op.create_index("ix_catalog_records_spotify_artist_id", "catalog_records", ["spotify_artist_id"])
    op.create_index("ix_catalog_records_title", "catalog_records", ["title"])
    op.create_index("ix_catalog_records_track_id", "catalog_records", ["track_id"])
    op.create_index("ix_catalog_records_year", "catalog_records", ["year"])
    op.create_table(
        "provider_metadata",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("status", sa.String(), primary_key=False, nullable=False),
        sa.Column("payload", sa.JSON(), primary_key=False, nullable=True),
        sa.Column("fetched_at", sa.String(), primary_key=False, nullable=True),
        sa.Column("retry_at", sa.String(), primary_key=False, nullable=True),
    )
    op.create_table(
        "catalog_artifacts",
        sa.Column("record_id", sa.String(), sa.ForeignKey("catalog_records.id"), primary_key=True, nullable=False),
        sa.Column(
            "configuration_id", sa.String(), sa.ForeignKey("model_configurations.id"), primary_key=True, nullable=False
        ),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analysis_runs.id"), primary_key=False, nullable=False),
        sa.Column("content_hash", sa.String(), primary_key=False, nullable=False),
        sa.Column("sequence", sa.Integer(), primary_key=False, nullable=False),
    )
    op.create_index("ix_catalog_artifacts_analysis_id", "catalog_artifacts", ["analysis_id"])
    op.create_index("ix_catalog_artifacts_sequence", "catalog_artifacts", ["sequence"])
    op.create_table(
        "catalog_snapshots",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("analysis_id", sa.String(), sa.ForeignKey("analysis_runs.id"), primary_key=False, nullable=False),
        sa.Column("sequence", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("songs", sa.Integer(), primary_key=False, nullable=False),
        sa.Column("created_at", sa.String(), primary_key=False, nullable=True),
        sa.Column("active", sa.Boolean(), primary_key=False, nullable=True),
    )
    op.create_index("ix_catalog_snapshots_active", "catalog_snapshots", ["active"])
    op.create_index("ix_catalog_snapshots_analysis_id", "catalog_snapshots", ["analysis_id"])


def downgrade():
    op.drop_table("catalog_snapshots")
    op.drop_table("catalog_artifacts")
    op.drop_table("provider_metadata")
    op.drop_table("catalog_records")
