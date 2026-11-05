# Support

## Before opening an issue

Check [README.md](README.md) and [AI_CORE_INTEGRATION.md](AI_CORE_INTEGRATION.md). Include the application version or commit, Windows and Python versions, steps to reproduce, expected behavior, and the first relevant error message.

## Troubleshooting

- **The package cannot be imported:** activate the project virtual environment and install the project with `python -m pip install -e .`.
- **The application cannot start:** confirm that the installed dependencies are present and that the application-data directory is writable.
- **A RAW image cannot be previewed:** verify that the format is supported by the installed `rawpy`/LibRaw runtime and try a small sample image.
- **AI features are unavailable:** check the selected provider and its local endpoint in Settings. Local model binaries and weights must be supplied separately.
- **MCP tools are unavailable:** verify the configured command, keep the server disabled until reviewed, restart AI-Core after config changes, and approve tool calls in AI-Core.

## Privacy and safe reports

The application may access photographs and metadata on the local computer. Its database, thumbnails, and settings are stored in the user's application-data directory and are not part of this source repository.

Do not attach photographs, EXIF data, database files, full paths, API keys, tokens, or unredacted logs to an issue. Use synthetic sample files and remove identifying information before sharing configuration or screenshots.

## Licensing

This repository does not include a project license. Do not treat public visibility as permission to reuse or redistribute its contents.
