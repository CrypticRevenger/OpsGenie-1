"""add awaiting_script onboarding state + normalize preferred_language to locale codes

Multilingual support (language x script). Adds the second onboarding step's
state and migrates the existing free-text preferred_language values
("English"/"Hindi"/...) to composite locale codes (en / hi-Deva / hi-Latn /
or-Orya / or-Latn). A bare language becomes its Romanized variant — the
recommended default for WhatsApp — so "Hindi" -> hi-Latn.

Revision ID: a7f3e21c9b40
Revises: 9b2e57d1a4c8
Create Date: 2026-07-18

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f3e21c9b40"
down_revision: str | None = "9b2e57d1a4c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate doesn't detect additions to a native Postgres enum type —
    # hand-written, per the project's migration playbook. Safe inside a
    # transaction on Postgres 12+ as long as the new value isn't *used* in the
    # same transaction (the preferred_language UPDATEs below don't touch the
    # enum, so there's no conflict).
    op.execute("ALTER TYPE onboardingstate ADD VALUE IF NOT EXISTS 'awaiting_script'")

    # Normalize existing preferred_language free text to locale codes. Order
    # matters: map the known names first, then sweep anything left (legacy
    # title-cased free text, NULLs) to English.
    op.execute(
        "UPDATE companies SET preferred_language = 'en' "
        "WHERE preferred_language IS NULL OR btrim(preferred_language) = '' "
        "OR lower(preferred_language) IN ('en', 'english')"
    )
    op.execute(
        "UPDATE companies SET preferred_language = 'hi-Latn' "
        "WHERE lower(preferred_language) IN ('hi', 'hindi')"
    )
    op.execute(
        "UPDATE companies SET preferred_language = 'or-Latn' "
        "WHERE lower(preferred_language) IN ('or', 'odia', 'oriya')"
    )
    op.execute(
        "UPDATE companies SET preferred_language = 'en' "
        "WHERE preferred_language NOT IN "
        "('en', 'hi-Deva', 'hi-Latn', 'or-Orya', 'or-Latn')"
    )


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE, and the original free-text
    # language values can't be reconstructed from the normalized codes — this
    # migration is effectively one-way. No-op, same as every other additive
    # enum migration in this project.
    pass
