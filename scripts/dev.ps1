param(
    [Parameter(Position = 0)]
    [ValidateSet("dev", "test", "migrate", "lint", "format")]
    [string]$Command = "dev"
)

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

switch ($Command) {
    "dev" { uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 }
    "test" { uv run pytest }
    "migrate" { uv run alembic upgrade head }
    "lint" { uv run ruff check app tests }
    "format" { uv run ruff format app tests }
}
