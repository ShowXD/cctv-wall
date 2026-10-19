"""CPU reporting: the raw sample counts one saturated core as 100%."""
from __future__ import annotations

from cctv_wall.resources import ProcessUsage


class TestCpuBreakdown:
    def test_cores_used_is_the_percentage_expressed_in_cores(self):
        assert ProcessUsage(380.0, 100.0, 16).cores_used == 3.8

    def test_machine_percent_divides_the_load_across_every_core(self):
        assert ProcessUsage(400.0, 100.0, 16).machine_percent == 25.0

    def test_an_unknown_core_count_leaves_the_machine_share_unknown(self):
        assert ProcessUsage(400.0, 100.0, None).machine_percent is None

    def test_an_unavailable_sample_stays_unavailable(self):
        usage = ProcessUsage(None, None, 16)
        assert usage.cores_used is None and usage.machine_percent is None
