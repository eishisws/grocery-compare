# Residential IP note: Akamai instantly blocks GitHub Actions / datacenter IPs
# (headless or not), but a real browser at a house IP, single run, paced -
# passes fine.
#
# One-time setup (PowerShell, your own terminal):
#   1. Persist the DB url as a user env var (rotated password, once):
#        setx DATABASE_URL "postgresql+psycopg://postgres.fnqmian...:NEWPASSWORD@aws-0-us-east-2.pooler.supabase.com:6543/postgres"
#   2. Register the daily task (04:45 local - comfortable for jobs you never
#        have to think about):
#        schtasks /create /tn "grocery-compare nightly" /st 04:45 /sc daily /tr `
#          "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\sunwo\grocery-compare\price-getter\scripts\run_nightly.ps1"
#   3. Test right now:  powershell -File scripts/run_nightly.ps1
#
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:DATABASE_URL) {
    Write-Error "DATABASE_URL not set - see the setup comments at the top of this file."
}

& uv run price-getter
exit $LASTEXITCODE
