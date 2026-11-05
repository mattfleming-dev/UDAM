# AI-Core Integration

## AI Provider

In Universal Stock DAM, open Settings and select **AI-Core** as the AI Provider. The default API URL is `http://127.0.0.1:8080` and the default model is `auto`; AI-Core must be running on the same computer. Use **Test Provider** before generating metadata. Image metadata requests send the selected image to AI-Core, so its routing and privacy settings apply.

Llama.cpp remains available as the other provider.

## AI-Core Tools

AI-Core owns the chat and tool-calling flow. Universal Stock DAM exposes an MCP stdio server with these tools:

- `search_assets`: search filenames and catalog metadata.
- `get_asset_details`: read metadata, keywords, and tags for an asset ID.
- `list_calendar_events`: read events in a date/time range.
- `schedule_asset_event`: create an event and optionally link it to an asset.

Asset tools do not return full filesystem paths. Event creation is a local database change; schedule only when requested. AI-Core's MCP approval prompt remains required for each call.

The development MCP entry is in AI-Core's `config/mcp.json` and points at this checkout's `.venv`. It is disabled by default. Restart AI-Core after changing the MCP config, enable **Universal Stock DAM** in AI-Core's MCP controls, then enable MCP in Chat. Review and approve calls in AI-Core.

For an installed DAM build, use the packaged `UniversalStockDAM-MCP.exe` as the MCP command instead of the development Python command. It is installed beside `UniversalStockDAM.exe`. Set the MCP transport to `stdio; command=<full path to UniversalStockDAM-MCP.exe>; args=`; restart AI-Core and enable the server. The app installer does not change AI-Core configuration automatically.

## Calendar

The **Calendar** tab is on the right side of Universal Stock DAM. Create, edit, or delete scheduled events, link an event to a catalog asset, and use **Open Asset** to return to that image in the Inspector. Events are stored in the existing DAM database; deleting an asset removes its event link but preserves the scheduled event.