from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

from universal_stock_dam.db.manager import DatabaseManager


_TOOLS = [
    {
        "name": "search_assets",
        "description": "Search the digital asset library by filename, title, description, keywords, and other indexed metadata.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search phrase."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_asset_details",
        "description": "Read metadata for one catalog asset by its numeric asset ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"asset_id": {"type": "integer", "minimum": 1}},
            "required": ["asset_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_calendar_events",
        "description": "List scheduled DAM events in an ISO date/time range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "starts_after": {"type": "string", "description": "Inclusive ISO date or datetime."},
                "starts_before": {"type": "string", "description": "Exclusive ISO date or datetime."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["starts_after", "starts_before"],
            "additionalProperties": False,
        },
    },
    {
        "name": "schedule_asset_event",
        "description": "Schedule an event and optionally link it to a catalog asset. Use only when the user explicitly asks to schedule something.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 256},
                "starts_at": {"type": "string", "format": "date-time"},
                "ends_at": {"type": "string", "format": "date-time"},
                "description": {"type": "string", "maxLength": 4000},
                "asset_id": {"type": "integer", "minimum": 1},
            },
            "required": ["title", "starts_at", "ends_at"],
            "additionalProperties": False,
        },
    },
]


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _event_output(event: dict[str, object]) -> dict[str, object]:
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in event.items()
    }


def call_tool(name: str, arguments: dict[str, Any], database_manager: DatabaseManager) -> object:
    if name == "search_assets":
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        limit = max(1, min(int(arguments.get("limit", 10)), 25))
        rows, total = database_manager.query_candidates(search=query, page=1, page_size=limit)
        return {
            "total_matches": total,
            "assets": [
                {
                    "asset_id": int(row.id),
                    "filename": row.filename,
                    "extension": row.ext,
                    "title": row.vision.title if row.vision else "",
                    "description": row.vision.description if row.vision else "",
                    "keywords": row.vision.keywords if row.vision else [],
                }
                for row in rows
            ],
        }

    if name == "get_asset_details":
        asset_id = int(arguments["asset_id"])
        asset = database_manager.get_candidate_by_id(asset_id)
        if asset is None:
            raise ValueError(f"Asset {asset_id} was not found")
        return {
            "asset_id": int(asset.id),
            "filename": asset.filename,
            "extension": asset.ext,
            "width": asset.width,
            "height": asset.height,
            "captured_at": asset.captured_at.isoformat() if asset.captured_at else None,
            "is_favorite": asset.is_favorite,
            "title": asset.vision.title if asset.vision else "",
            "description": asset.vision.description if asset.vision else "",
            "keywords": asset.vision.keywords if asset.vision else [],
            "tags": [tag.name for tag in asset.tags],
        }

    if name == "list_calendar_events":
        starts_after = _parse_datetime(str(arguments["starts_after"]))
        starts_before = _parse_datetime(str(arguments["starts_before"]))
        if starts_before <= starts_after:
            raise ValueError("starts_before must be later than starts_after")
        limit = max(1, min(int(arguments.get("limit", 50)), 100))
        events = database_manager.list_calendar_events(starts_before, starts_after, limit=limit)
        return {"events": [_event_output(event) for event in events]}

    if name == "schedule_asset_event":
        asset_id = arguments.get("asset_id")
        event = database_manager.save_calendar_event(
            title=str(arguments.get("title", "")),
            description=str(arguments.get("description", "")),
            starts_at=_parse_datetime(str(arguments["starts_at"])),
            ends_at=_parse_datetime(str(arguments["ends_at"])),
            candidate_id=int(asset_id) if asset_id is not None else None,
        )
        return _event_output(event)

    raise ValueError(f"Unknown DAM tool: {name}")


def handle_message(message: dict[str, Any], database_manager: DatabaseManager) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result: object = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "universal-stock-dam", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": _TOOLS}
    elif method == "tools/call":
        params = message.get("params", {})
        if not isinstance(params, dict):
            params = {}
        try:
            name = str(params.get("name", ""))
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            output = call_tool(name, arguments, database_manager)
            result = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, default=str)}]}
        except Exception as exc:
            result = {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            }
    else:
        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    if request_id is None:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def run_stdio_server() -> None:
    database_manager = DatabaseManager()
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                continue
            response = handle_message(message, database_manager)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()