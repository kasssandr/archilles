@echo off
REM Quick script to inspect your RAG database on Windows
REM Double-click this file to run it!

echo ========================================
echo ARCHILLES RAG Database Inspector
echo ========================================
echo.

REM Set the RAG database path
set RAG_DB_PATH=D:\Calibre-Bibliothek\.archilles\rag_db

echo Using RAG database at: %RAG_DB_PATH%
echo.

REM Run the inspection script
python scripts\inspect_windows_rag.py

echo.
echo ========================================
echo Done! Press any key to close...
pause >nul
