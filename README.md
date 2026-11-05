# Universal Stock DAM (UDAM)

Universal Stock DAM is a desktop digital-asset manager for cataloguing, reviewing, and organizing stock photography. It supports local asset metadata, image inspection, collections, calendar events, export workflows, and optional AI-assisted metadata generation.

## Requirements

- Windows 10/11 x64
- Python 3.12 or later
- Optional model/runtime files for local AI-assisted features; these are not included

## Install and run from source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m universal_stock_dam
```

The app stores its database, settings, and thumbnails in the current user's application-data directory. Source-control snapshots of those files and any photographs are intentionally excluded.

## AI-Core integration

See [AI_CORE_INTEGRATION.md](AI_CORE_INTEGRATION.md) for configuring the optional AI-Core provider and MCP tools. MCP is opt-in and should remain disabled until its command and permissions have been reviewed.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest
```

## Windows builds

Build the desktop bundle with:

```powershell
.\build_windows.ps1
```

Build the installer with Inno Setup 6 installed:

```powershell
.\build_installer.ps1
```

Model weights, local databases, photographs, runtime DLLs, and compiled installers are not tracked in this repository. See [SUPPORT.md](SUPPORT.md) before reporting build or runtime problems.

## License

No project license is included. Public visibility does not grant permission to reuse or redistribute this code.
