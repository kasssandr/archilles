# Quick script to inspect your RAG database on Windows
# Right-click -> Run with PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ARCHILLES RAG Database Inspector" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set the RAG database path
$env:RAG_DB_PATH = "D:\Calibre-Bibliothek\.archilles\rag_db"

Write-Host "Using RAG database at: $env:RAG_DB_PATH" -ForegroundColor Green
Write-Host ""

# Run the inspection script
python scripts\inspect_windows_rag.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Done! Press any key to close..." -ForegroundColor Cyan
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
