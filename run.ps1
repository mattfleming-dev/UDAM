# Run Universal Stock DAM from any terminal
$env:PYTHONPATH = (Get-Item $PSScriptRoot).Parent.FullName
& "$PSScriptRoot\.venv\Scripts\python.exe" -m universal_stock_dam @args
