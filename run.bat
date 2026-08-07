@echo off
rem PMD Spindle Runout - double-click to launch (uses uv-managed environment)
cd /d "%~dp0"
uv run pmd-runout %*
if errorlevel 1 pause
