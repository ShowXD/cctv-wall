"""AI result feed: parsing, time alignment, config, and a real loopback connection."""
from __future__ import annotations

import queue
import socket
import threading
from collections import deque
from datetime import datetime

import pytest

from cctv_wall.ai_feed import (DEFAULT_DELAY_MS, STATUS_CONNECTED, AiEvent, AiFeedClient,
                               AiFeedConfig, parse_line, parse_time, release_due)
from cctv_wall.models import Site, Workspace
from cctv_wall.ui.ai_feed_editor import FeedForm, config_from_form, feeds_from_forms

CONFIG = AiFeedConfig(host="127.0.0.1", port=9000)


class TestParseTime:
    @pytest.mark.parametrize("value,expected", [
        (1760860000, 1760860000.0),
        (1760860000.5, 1760860000.5),
        (1760860000500, 1760860000.5),            # milliseconds
        ("1760860000", 1760860000.0),
        ("2025-10-19T07:46:40Z", 1760860000.0),
        ("2025-10-19T15:46:40+08:00", 1760860000.0),
    ])
    def test_supported_formats(self, value, expected):
        assert parse_time(value) == pytest.approx(expected)

    def test_iso_time_without_zone_is_local(self):
        local = datetime(2025, 10, 19, 15, 46, 40)
        assert parse_time(local.isoformat()) == pytest.approx(local.timestamp())

    @pytest.mark.parametrize("value", [None, "", "yesterday", True, [1]])
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
        assert event.camera == "3" and event.event_time is None and event.text == "ts=5"

    def test_large_skew_is_flagged(self):
        event = parse_line('{"camera": "Gate", "ts": 100}', CONFIG, received_at=110.0)
        assert event.has_clock_skew

    @pytest.mark.parametrize("line", ["not json", "[1, 2]", '{"label": "person"}', '{"camera": " "}'])
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
        assert event.camera == "Front Gate"
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
        line = '{"eventType":4,"cameraName":"A009","payload":[]}'
        assert parse_line(line, SAMPLE, received_at=0.0) is None

    def test_tables_survive_a_round_trip(self):
        assert AiFeedConfig.from_raw(SAMPLE.as_dict()) == SAMPLE


class TestReleaseDue:
    def test_events_wait_for_the_video_delay(self):
        pending = deque([AiEvent("A", "", 10.0), AiEvent("B", "", 10.5)])
        assert release_due(pending, now=11.0, delay_ms=1500) == []
        assert [e.camera for e in release_due(pending, now=11.5, delay_ms=1500)] == ["A"]
        assert [e.camera for e in release_due(pending, now=12.0, delay_ms=1500)] == ["B"]
        assert not pending

    def test_zero_delay_releases_immediately(self):
        pending = deque([AiEvent("A", "", 10.0)])
        assert len(release_due(pending, now=10.0, delay_ms=0)) == 1


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
    def test_receives_lines_and_reconnects(self):
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
            assert events.get(timeout=5).camera == "A"
            assert events.get(timeout=5).camera == "B"   # after the 1 s backoff
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
