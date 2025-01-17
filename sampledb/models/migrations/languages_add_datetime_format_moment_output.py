# coding: utf-8
"""
Add datetime_format_moment_output column to languages table.
"""

import os

MIGRATION_INDEX = 102
MIGRATION_NAME, _ = os.path.splitext(os.path.basename(__file__))


def run(db):
    # Skip migration by condition
    languages_column_names = db.session.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'languages'
    """).fetchall()
    if ('datetime_format_moment_output',) in languages_column_names:
        return False

    # Perform migration
    db.session.execute("""
        ALTER TABLE languages
        ADD datetime_format_moment_output TEXT NOT NULL DEFAULT 'lll'
    """)
    db.session.execute("""
        UPDATE languages
        SET datetime_format_moment_output = 'MMM D, YYYY, h:mm:ss A'
        WHERE id = -99
    """)
    db.session.execute("""
        UPDATE languages
        SET datetime_format_moment_output = 'DD.MM.YYYY HH:mm:ss'
        WHERE id = -98
    """)
    return True
