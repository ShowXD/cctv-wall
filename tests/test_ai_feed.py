"""AI result feed: parsing, time alignment, config, and a real loopback connection."""
from __future__ import annotations

import queue
import socket
import threading
from collections import deque
from dataclasses import replace
from datetime import datetime

import pytest

from cctv_wall.ai_feed import (ALIGN_AI_TIME, ALIGN_RECEIVED, DEFAULT_DELAY_MS, STATUS_CONNECTED, AiEvent, AiFeedClient,
                               AiFeedConfig, due_at, parse_line, parse_time, release_due)
from cctv_wall.models import Site, Workspace
from cctv_wall.ui.ai_feed_editor import FeedForm, config_from_form, feeds_from_forms, label_fields
from cctv_wall.ui.ai_panel import short_camera_name, wrappable

CONFIG = AiFeedConfig(host="127.0.0.1", port=9000)


class TestParseTime:
    @pytest.mark.parametrize("value,expected", [
        (1760860000, 1760860000.0),
        (1760860000500, 1760860000.5),            # milliseconds
        ("1760860000", 1760860000.0),
        ("2025-10-19T07:46:40Z", 1760860000.0),
    ])
    def test_supported_formats(self, value, expected):
        assert parse_time(value) == pytest.approx(expected)

    def test_iso_time_without_zone_is_local(self):
        local = datetime(2025, 10, 19, 15, 46, 40)
        assert parse_time(local.isoformat()) == pytest.approx(local.timestamp())

    @pytest.mark.parametrize("value", [None, "yesterday", True])
    def test_unreadable_time_is_none(self, value):
        assert parse_time(value) is None


class TestParseLine:
    def test_camera_time_and_remaining_fields(self):
        event = parse_line('{"camera": "Gate", "ts": 1760860000, "label": "person", "conf": 0.92}',
                           CONFIG, received_at=1760860001.0)
        assert event == AiEvent("Gate", "label=person  conf=0.92", 1760860001.0, 1760860000.0)
        assert event.clock_skew == pytest.approx(1.0)
        assert not event.has_clock_skew

    def test_custom_keys(self):
        config = AiFeedConfig(host="h", port=1, camera_key="cam_id", time_key="")
        event = parse_line('{"cam_id": 3, "ts": 5}', config, received_at=10.0)
        assert event.camera_label == "3" and event.event_time is None and event.text == "ts=5"

    def test_large_skew_is_flagged(self):
        event = parse_line('{"camera": "Gate", "ts": 100}', CONFIG, received_at=110.0)
        assert event.has_clock_skew

    @pytest.mark.parametrize("line", ["not json", "[1, 2]", '{"camera": " "}'])
    def test_bad_lines_are_skipped(self, line):
        assert parse_line(line, CONFIG, received_at=0.0) is None

    def test_a_repeated_problem_is_logged_once(self, caplog):
        warned: set[str] = set()
        for _ in range(3):
            parse_line("not json", CONFIG, 0.0, warned)
        assert len([r for r in caplog.records if "not JSON" in r.getMessage()]) == 1


# The real project: two connections that both number their cameras A001/A002.
SAMPLE = AiFeedConfig.from_raw({
    "host": "192.168.1.50", "port": 9000, "camera_key": "cameraName", "time_key": "created",
    "cameras": {"A001": "Front Gate", "A002": "Lobby"}, "skip_empty": ["payload"],
    "labels": {"eventType": {"1": "距離偵測", "2": "淨空區狀態", "4": "路口停等偵測"},
               "vdType": {"2": "汽車", "7": "腳踏車"}}})


class TestRealSample:
    def test_detection_is_mapped_and_rendered_as_json(self):
        line = ('{"eventType":4,"cameraName":"A001","created":"2026-10-19 12:10:49.750",'
                '"payload":[{"duration":0,"id":-1,"trackingId":667814,"vdType":2}]}')
        event = parse_line(line, SAMPLE, received_at=0.0)
        assert event.camera_label == "Front Gate"
        assert event.event_time == pytest.approx(datetime(2026, 10, 19, 12, 10, 49, 750000).timestamp())
        assert event.text == ('eventType=路口停等偵測  payload=[{"duration":0,"id":-1,'
                              '"trackingId":667814,"vdType":"汽車"}]')

    def test_a_code_without_a_label_is_kept(self):
        line = '{"eventType":3,"cameraName":"A002","payload":[{"vdType":5}]}'
        assert parse_line(line, SAMPLE, received_at=0.0).text == 'eventType=3  payload=[{"vdType":5}]'

    def test_an_empty_payload_is_skipped_whatever_the_event(self):
        for event_type in (2, 4):
            line = f'{{"eventType":{event_type},"cameraName":"A002","payload":[]}}'
            assert parse_line(line, SAMPLE, received_at=0.0) is None

    def test_skip_by_value(self):
        config = AiFeedConfig.from_raw({"host": "h", "port": 1, "skip": {"eventType": [2, 3]}})
        assert parse_line('{"camera":"A","eventType":3}', config, received_at=0.0) is None
        assert parse_line('{"camera":"A","eventType":4}', config, received_at=0.0) is not None

    def test_an_id_missing_from_the_table_is_skipped(self):
        line = '{"eventType":4,"cameraName":"A009","payload":[{"vdType":2}]}'
        assert parse_line(line, SAMPLE, received_at=0.0) is None

    def test_tables_survive_a_round_trip(self):
        assert AiFeedConfig.from_raw(SAMPLE.as_dict()) == SAMPLE


class TestReleaseDue:
    BY_ARRIVAL = AiFeedConfig(host="h", port=1, delay_ms=1500, align=ALIGN_RECEIVED)
    BY_AI_TIME = AiFeedConfig(host="h", port=1, delay_ms=1500, align=ALIGN_AI_TIME)

    def test_events_wait_for_the_video_delay(self):
        pending = deque([AiEvent("A", "", 10.0), AiEvent("B", "", 10.5)])
        assert release_due(pending, now=11.0, config=self.BY_ARRIVAL) == []
        assert [e.camera_label for e in release_due(pending, now=11.5, config=self.BY_ARRIVAL)] == ["A"]
        assert [e.camera_label for e in release_due(pending, now=12.0, config=self.BY_ARRIVAL)] == ["B"]
        assert not pending

    def test_zero_delay_releases_immediately(self):
        pending = deque([AiEvent("A", "", 10.0)])
        assert len(release_due(pending, now=10.0, config=replace(self.BY_ARRIVAL, delay_ms=0))) == 1

    def test_aligned_to_ai_time_a_slow_ai_does_not_push_the_result_later(self):
        # Analysed at 10.0, arrived 0.8 s later: shown at 10.0 + 1.5, not 10.8 + 1.5.
        pending = deque([AiEvent("A", "", received_at=10.8, event_time=10.0)])
        assert [e.camera_label for e in release_due(pending, now=11.5, config=self.BY_AI_TIME)] == ["A"]

    def test_without_a_usable_ai_time_it_falls_back_to_arrival(self):
        assert due_at(AiEvent("A", "", 10.8), self.BY_AI_TIME) == 12.3
        assert due_at(AiEvent("A", "", 10.8, event_time=1.0), self.BY_AI_TIME) == 12.3   # clocks apart

    def test_a_config_without_align_keeps_the_old_arrival_behaviour(self):
        assert AiFeedConfig.from_raw({"host": "h", "port": 1}).align == ALIGN_RECEIVED
        assert AiFeedConfig.from_raw(self.BY_AI_TIME.as_dict()) == self.BY_AI_TIME


class TestConfig:
    def test_defaults(self):
        config = AiFeedConfig.from_raw({"host": "10.0.0.9", "port": "9000"})
        assert (config.camera_key, config.time_key, config.delay_ms) == ("camera", "ts", DEFAULT_DELAY_MS)

    @pytest.mark.parametrize("raw,message", [
        ({"port": 9000}, "needs a host"),
        ({"host": "h"}, "port must be"),
        ({"host": "h", "port": "x"}, "whole number"),
        ({"host": "h", "port": 1, "delay_ms": -1}, "delay_ms"),
    ])
    def test_invalid(self, raw, message):
        with pytest.raises(ValueError, match=message):
            AiFeedConfig.from_raw(raw)

    def test_site_round_trip_keeps_every_feed(self):
        raw = {"name": "Lab", "cameras": [{"name": "A", "host": "10.0.0.1"}],
               "ai_feeds": [{"host": "10.0.0.9", "port": 9000, "delay_ms": 800},
                            {"host": "10.0.0.10", "port": 9000}]}
        site = Site.from_raw(raw)
        assert [feed.delay_ms for feed in site.ai_feeds] == [800, DEFAULT_DELAY_MS]
        assert Site.from_raw(site.as_dict()) == site

    def test_site_without_feed_writes_no_key(self):
        assert "ai_feeds" not in Site.from_raw({"name": "Lab"}).as_dict()

    def test_feed_requires_unique_camera_names(self):
        raw = {"name": "Lab", "ai_feeds": [{"host": "h", "port": 1}],
               "cameras": [{"name": "A", "host": "10.0.0.1"}, {"name": "A", "host": "10.0.0.2"}]}
        with pytest.raises(ValueError, match="unique"):
            Workspace.from_raw({"sites": [raw]})

    def test_unnamed_cameras_are_mapped_and_told_apart_by_their_address(self):
        feeds = [{"host": "h", "port": 1, "cameras": {"A001": "rtsp://10.0.0.1/s"}}]
        two = [{"url": "rtsp://10.0.0.1/s"}, {"url": "rtsp://10.0.0.2/s"}]
        Site.from_raw({"name": "Lab", "cameras": two, "ai_feeds": feeds})
        with pytest.raises(ValueError, match="unique"):
            Site.from_raw({"name": "Lab", "cameras": [two[0], two[0]], "ai_feeds": feeds})

    def test_one_camera_cannot_be_mapped_by_two_feeds(self):
        raw = {"name": "Lab", "ai_feeds": [
            {"host": "h1", "port": 1, "cameras": {"A001": "Gate"}},
            {"host": "h2", "port": 1, "cameras": {"A001": "Gate"}}]}
        with pytest.raises(ValueError, match="mapped more than once"):
            Site.from_raw(raw)

    def test_a_bad_feed_names_its_position(self):
        with pytest.raises(ValueError, match=r"ai_feeds\[1\]: ai_feed needs a host"):
            Site.from_raw({"name": "Lab", "ai_feeds": [{"host": "h", "port": 1}, {"port": 1}]})


class TestClient:
    def test_receives_lines_and_reconnects(self, monkeypatch):
        monkeypatch.setattr("cctv_wall.ai_feed.FIRST_BACKOFF_SECONDS", 0.05)
        server = socket.create_server(("127.0.0.1", 0))
        events: queue.Queue = queue.Queue()
        statuses: queue.Queue = queue.Queue()

        def serve() -> None:
            for camera in (b"A", b"B"):  # two connections: the second proves the reconnect
                conn, _ = server.accept()
                with conn:
                    conn.sendall(b'not json\n{"camera": "' + camera + b'", "ts": 1}\n')

        threading.Thread(target=serve, daemon=True).start()
        client = AiFeedClient(AiFeedConfig("127.0.0.1", server.getsockname()[1]),
                              events.put, statuses.put)
        client.start()
        try:
            assert events.get(timeout=5).camera_label == "A"
            assert events.get(timeout=5).camera_label == "B"   # after the first backoff
            assert STATUS_CONNECTED in list(statuses.queue)
        finally:
            client.stop()
            server.close()

    def test_stop_interrupts_a_blocking_read(self):
        server = socket.create_server(("127.0.0.1", 0))
        accepted = threading.Event()

        def serve() -> None:
            conn, _ = server.accept()
            accepted.set()
            conn.recv(1)  # hold the connection open until the client closes it
            conn.close()

        threading.Thread(target=serve, daemon=True).start()
        client = AiFeedClient(AiFeedConfig("127.0.0.1", server.getsockname()[1]),
                              lambda _event: None, lambda _status: None)
        client.start()
        assert accepted.wait(5)
        client.stop()
        client._thread.join(5)
        server.close()
        assert not client._thread.is_alive()


class TestDialogForm:
    """The settings dialog's form <-> config conversion, without opening a window."""

    def test_round_trip_keeps_format_and_mapping(self):
        assert config_from_form(FeedForm.from_config(SAMPLE)) == SAMPLE

    def test_blank_mapping_rows_are_ignored(self):
        form = FeedForm("h", "9000", 0, [("", ""), ("A001", "Gate")], "")
        assert config_from_form(form).cameras == (("A001", "Gate"),)

    @pytest.mark.parametrize("mapping,advanced,message", [
        ([("A001", "")], "", "needs both"),
        ([("A001", "Gate"), ("A001", "Lobby")], "", "mapped twice"),
        ([], "{not json", "not valid JSON"),
        ([], "[]", "must be a JSON object"),
        ([], '{"camera_kye": "x"}', "unknown advanced setting"),
    ])
    def test_invalid_forms(self, mapping, advanced, message):
        with pytest.raises(ValueError, match=message):
            config_from_form(FeedForm("h", "9000", 0, mapping, advanced))

    def test_site_rules_apply_across_connections(self):
        forms = [FeedForm("h1", "1", 0, [("A001", "Gate")]), FeedForm("h2", "1", 0, [("A001", "Gate")])]
        with pytest.raises(ValueError, match="mapped more than once"):
            feeds_from_forms("Lab", (), forms)

    def test_the_failing_connection_is_named(self):
        with pytest.raises(ValueError, match="#2 h2: ai_feed port"):
            feeds_from_forms("Lab", (), [FeedForm("h1", "1"), FeedForm("h2", "99999")])


class TestPanelText:
    def test_an_unnamed_camera_is_shown_by_its_host(self):
        assert short_camera_name("rtsp://192.168.101.1/stream2") == "192.168.101.1"
        assert short_camera_name("Gate") == "Gate"

    def test_compact_json_gets_break_points_but_reads_the_same(self):
        text = 'payload=[{"id":-1,"vdType":"機車"}]'
        assert wrappable(text).replace("​", "") == text
        assert wrappable(text).count("​") == text.count(",")


class TestTileRows:
    LABELS = {"eventType": {"1": "距離偵測", "4": "路口停等偵測"}}

    def _config(self, **extra):
        return AiFeedConfig.from_raw({"host": "h", "port": 1, "camera_key": "cameraName",
                                      "labels": self.LABELS, **extra})

    def test_each_ticked_kind_has_its_own_line_in_the_ticked_order(self):
        config = self._config(tile_key="eventType", tile_values=[4, "1"])
        assert [config.tile_row(kind) for kind in ("4", "1", "3")] == [0, 1, None]
        assert AiFeedConfig.from_raw(config.as_dict()) == config

    def test_without_ticked_kinds_every_result_shares_one_line(self):
        assert self._config().tile_row("3") == 0
        assert "tile_key" not in self._config().as_dict()

    def test_kinds_need_the_field_they_are_kinds_of(self):
        with pytest.raises(ValueError, match="tile_key"):
            self._config(tile_values=["4"])

    def test_the_kind_is_read_before_codes_become_text(self):
        config = self._config(tile_key="eventType", tile_values=["4"])
        event = parse_line('{"eventType":4,"cameraName":"A001"}', config, 0.0)
        assert event.group == "4" and "路口停等偵測" in event.text

    def test_the_dialog_offers_the_labelled_fields_and_keeps_the_choice(self):
        assert label_fields('{"labels": {"eventType": {"1": "距離偵測"}}}') == {"eventType": [("1", "距離偵測")]}
        assert label_fields('{"labels": ') is None   # half-typed: keep the old choices
        form = FeedForm("h", "1", advanced='{"camera_key": "cameraName"}', tile_key="eventType",
                        tile_values=["4"])
        assert config_from_form(form).tile_values == ("4",)

    def test_a_kind_inside_payload_takes_its_line_ticked_kinds_first(self):
        config = self._config(tile_key="vdType", tile_values=["2", "5"])
        event = parse_line('{"cameraName":"A001","payload":[{"vdType":3},{"vdType":5}]}', config, 0.0)
        assert config.tile_row(event.group) == 1

    def test_every_connection_of_every_site_gets_the_same_kinds(self):
        feed = self._config()
        workspace = Workspace.from_raw({"sites": [
            {"name": "A", "ai_feeds": [feed.as_dict()]}, {"name": "B", "ai_feeds": [feed.as_dict()]}]})
        updated = workspace.with_ai_tile_rows("eventType", ("4",))
        assert {f.tile_values for site in updated.sites for f in site.ai_feeds} == {("4",)}


class TestCameraFilters:
    def _config(self):
        return AiFeedConfig.from_raw({"host": "h", "port": 1, "camera_key": "cameraName",
                                      "cameras": {"A001": "Gate", "A002": "Yard"},
                                      "camera_filters": {"A001": {"vdType": [2, "5"]}}})

    @pytest.mark.parametrize("line,shown", [
        ('{"cameraName":"A001","payload":[{"vdType":3},{"vdType":5}]}', True),
        ('{"cameraName":"A001","payload":[{"vdType":3}]}', False),
        ('{"cameraName":"A001","eventType":2}', False),    # without the field: not shown
        ('{"cameraName":"A002","payload":[{"vdType":3}]}', True),   # other cameras unaffected
    ])
    def test_only_the_ticked_values_of_that_camera_pass(self, line, shown):
        assert (parse_line(line, self._config(), 0.0) is not None) == shown

    def test_round_trip_and_dialog(self):
        config = self._config()
        assert AiFeedConfig.from_raw(config.as_dict()) == config
        form = FeedForm.from_config(config)
        assert form.filters == {"A001": ("vdType", ["2", "5"])}
        assert config_from_form(form) == config

    def test_a_filter_must_belong_to_a_mapped_camera(self):
        with pytest.raises(ValueError, match="A009"):
            AiFeedConfig.from_raw({"host": "h", "port": 1, "cameras": {"A001": "Gate"},
                                   "camera_filters": {"A009": {"vdType": ["2"]}}})
