@echo off
REM Quick test of your RAG database
REM Double-click this file to run a test query!

echo ========================================
echo ARCHILLES RAG Test Query
echo ========================================
echo.

REM Set the paths
set RAG_DB_PATH=D:\Calibre-Bibliothek\.archilles\rag_db
set CALIBRE_LIBRARY_PATH=D:\Calibre-Bibliothek

echo RAG Database: %RAG_DB_PATH%
echo Calibre Library: %CALIBRE_LIBRARY_PATH%
echo.
echo Running test query: "David Melchizedek"
echo.

REM Run a test query
python scripts\rag_demo.py query "David Melchizedek" --mode hybrid --top-k 5

echo.
echo ========================================
echo Done! Press any key to close...
pause >nul
