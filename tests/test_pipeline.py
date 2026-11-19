import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from pipeline import generate, process, persist, summary

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.good = pd.DataFrame([dict(sensor_id='S01',timestamp='2026-01-01T00:00:00Z',temperature=25,pressure=100,voltage=3.7)])

    def test_reproducible_generator(self):
        pd.testing.assert_frame_equal(generate(20, 9), generate(20, 9))

    def test_normal_measurement(self):
        row = process(self.good).iloc[0]
        self.assertEqual(row.status, 'normal')
        self.assertEqual(row.risk_score, 0)

    def test_out_of_range_invalid_not_abnormal(self):
        df = self.good.copy(); df.loc[0,'temperature'] = 120
        row = process(df).iloc[0]
        self.assertEqual(row.status, 'invalid')
        self.assertTrue(pd.isna(row.risk_score))

    def test_missing_field_invalid(self):
        df = self.good.copy(); df.loc[0,'pressure'] = float('nan')
        self.assertEqual(process(df).iloc[0].status, 'invalid')

    def test_abnormal_risk(self):
        df = self.good.copy(); df.loc[0,'temperature'] = 48
        row = process(df).iloc[0]
        self.assertEqual((row.status, row.risk_score), ('abnormal', 30))

    def test_two_abnormal_risk(self):
        df = self.good.copy(); df.loc[0,'temperature'] = 48; df.loc[0,'voltage'] = 4.8
        self.assertEqual(process(df).iloc[0].risk_score, 60)

    def test_missing_column(self):
        with self.assertRaises(ValueError): process(self.good.drop(columns=['voltage']))

    def test_sqlite_integration(self):
        df = process(generate(20))
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'readings.sqlite'
            persist(df, db)
            with sqlite3.connect(db) as conn:
                total = conn.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
                invalid = conn.execute("SELECT COUNT(*) FROM readings WHERE status='invalid'").fetchone()[0]
            self.assertEqual(total, 20)
            self.assertEqual(invalid, summary(df)['invalid'])

    def test_cli_replay_and_distinct_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "readings.sqlite"
            csv = Path(tmp) / "processed.csv"
            pipeline = Path(__file__).resolve().parents[1] / "pipeline.py"
            command = [
                sys.executable, str(pipeline), "--n", "20",
                "--db", str(db), "--csv", str(csv),
            ]
            for seed, expected in [(42, 20), (42, 20), (43, 40)]:
                with self.subTest(seed=seed, expected=expected):
                    subprocess.run(
                        [*command, "--seed", str(seed)], check=True, capture_output=True
                    )
                    with sqlite3.connect(db) as conn:
                        total = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
                    self.assertEqual(total, expected)
                    self.assertEqual(len(pd.read_csv(csv)), 20)


if __name__ == '__main__': unittest.main()
