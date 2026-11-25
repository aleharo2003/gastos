import unittest

from retain_backups import deletion_ids


class RetentionTests(unittest.TestCase):
    def test_preserves_eight_distinct_weeks_and_newest_retry(self):
        copies = [{'id': week, 'name': f'piggo-postgres-2026-W{week:02d}-r1', 'expired': False}
                  for week in range(1, 11)]
        copies += [
            {'id': 11, 'name': 'piggo-postgres-2026-W10-r2', 'expired': False},
            {'id': 12, 'name': 'otro-workflow', 'expired': False},
            {'id': 13, 'name': 'piggo-postgres-2025-W52-r1', 'expired': True},
        ]
        self.assertCountEqual(deletion_ids(copies, 11), [1, 2, 10])

    def test_keeps_existing_backups_if_upload_cannot_be_confirmed(self):
        copies = [{'id': 1, 'name': 'piggo-postgres-2026-W01-r1', 'expired': False}]
        with self.assertRaises(ValueError):
            deletion_ids(copies, 2)
