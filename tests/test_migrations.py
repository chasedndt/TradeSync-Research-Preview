import unittest
from pathlib import Path

from ops.migrate import migration_files, up_sql


ROOT = Path(__file__).resolve().parents[1]

# Numbers no migration will ever carry.
#
# 035 was reserved for the paper gaps branch of 2026-09-16, which turned out to
# need no schema change (the kill audit reuses the existing close action and part
# fills live in JSONB), so the number was never used. 036 and 037 keep the numbers
# they were written, verified and documented under; renaming them would make three
# change records describe acceptance runs that were never performed under those
# names. A gap at a skipped number is allowed; any other gap still fails, and the
# runner applies pending versions in order regardless, so a gap is safe to deploy.
#
# 038 arrived with the mobile PWA branch. 039 and 040 were held for other branches
# of 2026-09-16 that turned out to need no schema change; every one of them is
# merged, so both numbers are released and the next migration is 039.
SKIPPED_MIGRATION_NUMBERS: set[str] = {"035"}


class MigrationRunnerTests(unittest.TestCase):
    def test_up_parser_never_includes_down_statements(self):
        sql = up_sql("-- UP\ncreate table safe(id int);\n-- DOWN\ndrop table safe;")
        self.assertIn("create table safe", sql)
        self.assertNotIn("drop table", sql)

    def test_all_repository_migrations_have_parseable_up_sections(self):
        """Assert the invariants, not a fixed list.

        A hard-coded roster fails every time a migration is added, which says
        nothing about whether the migrations are well formed.
        """
        files = migration_files(ROOT / "ops/migrations")
        self.assertTrue(files, "no migrations found")
        prefixes = [path.name[:3] for path in files]

        # Numbered from 001, contiguous apart from reserved numbers, unique,
        # and already in order.
        self.assertEqual(prefixes, sorted(prefixes), "migrations must be ordered")
        self.assertEqual(len(set(prefixes)), len(prefixes), "duplicate prefix")
        self.assertEqual(prefixes[0], "001", "migration numbering must start at 001")
        missing = [
            number
            for number in (f"{i:03d}" for i in range(1, int(prefixes[-1]) + 1))
            if number not in set(prefixes)
        ]
        self.assertEqual(
            [number for number in missing if number not in SKIPPED_MIGRATION_NUMBERS],
            [],
            "migration numbering must be contiguous from 001",
        )
        for path in files:
            self.assertTrue(
                up_sql(path.read_text(encoding="utf-8-sig")),
                f"{path.name} has no parseable UP section",
            )


if __name__ == "__main__":
    unittest.main()
