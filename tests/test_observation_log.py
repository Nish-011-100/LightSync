import unittest
import tempfile
from pathlib import Path
import pandas as pd
from src.observation_log import save,read
class ObservationLogTests(unittest.TestCase):
    def test_persistence_and_invalid_future(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            record=dict(record_id='test-id',observed_at_ist=(pd.Timestamp.now(tz='Asia/Kolkata')-pd.Timedelta(minutes=1)).isoformat(),observer_alias='observer-a',installed_count=10,nonworking_count=1)
            save(root,record)
            self.assertEqual(read(root).iloc[0].observer_alias,'observer-a')
            record['record_id']='future';record['observed_at_ist']=(pd.Timestamp.now(tz='Asia/Kolkata')+pd.Timedelta(days=1)).isoformat()
            with self.assertRaises(ValueError):save(root,record)
            self.assertEqual(len(read(root)),1)
    def test_invalid_counts(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):save(Path(d),dict(observed_at_ist='2026-01-01T00:00:00+05:30',installed_count=2,nonworking_count=3))
