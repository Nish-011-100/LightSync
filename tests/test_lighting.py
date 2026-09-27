"""Meaningful accounting and transition checks. Run python -m unittest discover -s tests."""
import unittest
import numpy as np
import pandas as pd
from src.lighting import interval_impact, propose_interval


class LightingTests(unittest.TestCase):
    def setUp(self):
        self.t = lambda x: pd.Timestamp(x, tz='Asia/Kolkata')

    def impact(self, a, b, c, d, count=10):
        return interval_impact(*[self.t(x) for x in [a,b,c,d]], power_w=100, working_count=count)

    def test_identical_intervals_no_savings(self):
        r=self.impact('2026-09-25 17:00','2026-09-26 06:00','2026-09-25 17:00','2026-09-26 06:00')
        self.assertEqual(r['net_savings_kwh'],0)
        self.assertEqual(r['manual_kwh'],13)

    def test_shorter_schedule_reconciles(self):
        r=self.impact('2026-09-25 17:00','2026-09-26 06:00','2026-09-25 17:30','2026-09-26 05:30')
        self.assertEqual(r['excess_kwh'],1)
        self.assertEqual(r['additional_kwh'],0)

    def test_underlighting_correction_can_cost_energy(self):
        r=self.impact('2026-09-25 18:00','2026-09-26 05:00','2026-09-25 17:00','2026-09-26 06:00')
        self.assertEqual(r['additional_kwh'],2)
        self.assertEqual(r['net_savings_kwh'],-2)

    def test_shift_has_both_added_and_excess(self):
        r=self.impact('2026-09-25 17:00','2026-09-26 05:00','2026-09-25 18:00','2026-09-26 06:00')
        self.assertEqual(r['excess_kwh'],1)
        self.assertEqual(r['additional_kwh'],1)
        self.assertEqual(r['net_savings_kwh'],0)

    def test_zero_working_lights_no_savings_credit(self):
        r=self.impact('2026-09-25 17:00','2026-09-26 06:00','2026-09-25 18:00','2026-09-26 05:00',0)
        self.assertEqual(r['manual_kwh'],0)
        self.assertEqual(r['net_savings_kwh'],0)

    def test_astronomical_guards_and_persistence(self):
        ts=pd.date_range(self.t('2026-09-25 12:00'),periods=1440,freq='min')
        lux=np.full(1440,1000.)
        frame=pd.DataFrame({'timestamp_local':ts,'lux_proxy':lux})
        on,off,missing=propose_interval(frame,self.t('2026-09-25 17:16'),self.t('2026-09-26 05:14'),20,30,
                                       {'step_minutes':1,'stable_daylight_minutes':5,'switch_on_buffer_minutes':2,'switch_off_buffer_minutes':2})
        self.assertEqual(on,self.t('2026-09-25 17:16'))
        self.assertEqual(off,self.t('2026-09-26 05:16'))
        self.assertFalse(missing)

    def test_never_bright_enough_requires_review(self):
        ts=pd.date_range(self.t('2026-09-25 12:00'),periods=1440,freq='min')
        frame=pd.DataFrame({'timestamp_local':ts,'lux_proxy':np.zeros(1440)})
        on,off,missing=propose_interval(frame,self.t('2026-09-25 17:16'),self.t('2026-09-26 05:14'),20,30,
                                       {'step_minutes':1,'stable_daylight_minutes':5})
        self.assertTrue(missing)
        self.assertEqual(off,self.t('2026-09-26 12:00'))

    def test_minute_decisions_do_not_add_a_full_sampling_interval(self):
        ts=pd.date_range(self.t('2026-09-25 12:00'),periods=1440,freq='min')
        dark=(ts>=self.t('2026-09-25 17:07'))&(ts<self.t('2026-09-26 05:19'))
        frame=pd.DataFrame({'timestamp_local':ts,'lux_proxy':np.where(dark,0,1000)})
        on,off,missing=propose_interval(frame,self.t('2026-09-25 17:16'),self.t('2026-09-26 05:14'),20,30,
            {'step_minutes':1,'stable_daylight_minutes':5,'switch_on_buffer_minutes':2,'switch_off_buffer_minutes':2})
        self.assertEqual(on,self.t('2026-09-25 17:05'))
        self.assertEqual(off,self.t('2026-09-26 05:21'))
        self.assertFalse(missing)

    def test_morning_bright_spike_cannot_hide_later_darkness(self):
        ts=pd.date_range(self.t('2026-09-25 12:00'),periods=1440,freq='min')
        lux=np.full(1440,1000.)
        lux[(ts>=self.t('2026-09-26 05:40'))&(ts<self.t('2026-09-26 05:48'))]=0
        frame=pd.DataFrame({'timestamp_local':ts,'lux_proxy':lux})
        _,off,_=propose_interval(frame,self.t('2026-09-25 17:16'),self.t('2026-09-26 05:14'),20,30,
            {'step_minutes':1,'stable_daylight_minutes':5,'switch_off_buffer_minutes':2})
        self.assertEqual(off,self.t('2026-09-26 05:50'))


if __name__=='__main__':
    unittest.main()
