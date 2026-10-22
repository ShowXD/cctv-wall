"""試算表匯入／匯出：讀檔、猜欄位、逐列轉換、合併到工作區、匯出再匯回。"""
from __future__ import annotations

import pytest

from cctv_wall import camera_table
from cctv_wall.ai_feed import AiFeedConfig
from cctv_wall.models import Camera, Site, Workspace


def test_csv_reads_utf8_with_bom_and_big5(tmp_path):
    for encoding in ("utf-8-sig", "cp950"):
        path = tmp_path / f"{encoding}.csv"
        path.write_bytes("名稱,IP\n大門,192.0.2.10\n".encode(encoding))
        assert camera_table.read_rows(path) == [["名稱", "IP"], ["大門", "192.0.2.10"]]


def test_xlsx_round_trip_keeps_whole_numbers(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / "list.xlsx"
    workbook = Workbook()
    workbook.active.append(["IP", "Port"])
    workbook.active.append(["192.0.2.10", 554.0])
    workbook.save(path)
    assert camera_table.read_rows(path) == [["IP", "Port"], ["192.0.2.10", "554"]]


def test_guess_mapping_in_both_languages():
    assert camera_table.guess_mapping(["地點", "攝影機名稱", "IP 位址", "Port", "帳號", "密碼"]) == {
        "site": 0, "name": 1, "host": 2, "port": 3, "user": 4, "password": 5}
    assert camera_table.guess_mapping(["Name", "RTSP URL", "Username", "Password", "Notes"]) == {
        "name": 0, "url": 1, "user": 2, "password": 3}


def test_rows_build_cameras_from_url_or_ip_and_report_bad_rows():
    rows = [
        ["Gate", "rtsp://admin:pw@192.0.2.10:554/stream1", "", ""],
        ["", "", "", ""],
        ["Yard", "", "192.0.2.11", "8554"],
        ["Bad", "", "192.0.2.12", "port?"],
    ]
    mapping = {"name": 0, "url": 1, "host": 2, "port": 3}
    cameras, errors = camera_table.cameras_from_rows(rows, mapping, "hikvision", "Office", first_row=2)
    assert cameras == [
        ("Office", Camera("Gate", "rtsp://192.0.2.10:554/stream1", "admin", "pw")),
        ("Office", Camera("Yard", "rtsp://192.0.2.11:8554/Streaming/Channels/101")),
    ]
    assert [row for row, _error in errors] == [5]


def test_site_column_wins_over_default_site():
    cameras, errors = camera_table.cameras_from_rows(
        [["North", "rtsp://192.0.2.1/a"], ["", "rtsp://192.0.2.2/b"]],
        {"site": 0, "url": 1}, "generic", "Office")
    assert [site for site, _camera in cameras] == ["North", "Office"] and not errors


def test_merge_creates_sites_appends_and_skips_duplicates():
    existing = Camera("Gate", "rtsp://192.0.2.1/a")
    workspace = Workspace(sites=(Site("Office", (existing,)),))
    imported = [("Office", Camera("Again", "rtsp://192.0.2.1/a")),
                ("Office", Camera("Door", "rtsp://192.0.2.2/b")),
                ("Plant", Camera("Line", "rtsp://192.0.2.3/c"))]
    updated, added = camera_table.merge_into(workspace, imported)
    assert added == 2
    assert [c.name for c in updated.site("Office").cameras] == ["Gate", "Door"]
    assert [c.name for c in updated.site("Plant").cameras] == ["Line"]


def test_merge_refuses_duplicate_names_on_a_site_with_ai_feeds():
    feed = AiFeedConfig.from_raw({"host": "127.0.0.1", "port": 9000})
    workspace = Workspace(sites=(Site("Office", (Camera("Gate", "rtsp://192.0.2.1/a"),), (feed,)),))
    with pytest.raises(ValueError):
        camera_table.merge_into(workspace, [("Office", Camera("Gate", "rtsp://192.0.2.2/b"))])


@pytest.mark.parametrize("suffix", [".xlsx", ".csv"])
def test_export_then_import_gives_the_same_cameras(tmp_path, suffix):
    sites = (Site("辦公室", (Camera("大門", "rtsp://192.0.2.1/a", "admin", "pw"),)),)
    path = tmp_path / f"out{suffix}"
    header = ["地點", "名稱", "網址", "帳號", "密碼"]
    camera_table.write_rows(path, [header, *camera_table.table_rows(sites, True)])
    rows = camera_table.read_rows(path)
    cameras, errors = camera_table.cameras_from_rows(rows[1:], camera_table.guess_mapping(rows[0]),
                                                     "generic", "")
    assert cameras == [("辦公室", sites[0].cameras[0])] and not errors


def test_export_without_credentials_leaves_them_out():
    sites = (Site("Office", (Camera("Gate", "rtsp://192.0.2.1/a", "admin", "pw"),)),)
    assert camera_table.table_rows(sites, False) == [["Office", "Gate", "rtsp://192.0.2.1/a"]]
