from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from universal_stock_dam.db.manager import DatabaseManager
from mcp_server import call_tool, handle_message


def test_mcp_tool_inventory_and_approval_compatible_call(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))
    image = tmp_path / "asset.jpg"
    image.write_bytes(b"image")
    candidate = manager.add_or_update_candidate(str(image), image.name, "jpg")

    listing = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, manager)
    assert listing is not None
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert names == {"search_assets", "get_asset_details", "list_calendar_events", "schedule_asset_event"}

    start = datetime(2031, 9, 5, 10, 0)
    response = handle_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "schedule_asset_event",
            "arguments": {
                "title": "Publish asset",
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(),
                "asset_id": candidate.id,
            },
        },
    }, manager)

    assert response is not None
    assert response["id"] == 3
    assert '"candidate_id": ' + str(candidate.id) in response["result"]["content"][0]["text"]
    assert call_tool("get_asset_details", {"asset_id": candidate.id}, manager)["filename"] == image.name


def test_mcp_notifications_do_not_emit_responses(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, manager) is None