# Smart Screenshot Organizer dashboard

The dashboard monitors the independent automation service. Opening, refreshing or closing
Streamlit does not start or stop a watcher. Only the explicit Live Monitor controls invoke
the existing `background.py start` or `stop` commands, which retain the source lock and
graceful shutdown behavior. The OCR and screenshot-processing pipeline is unchanged.

## Run on Windows

From PowerShell:

```powershell
Set-Location 'C:\Users\iqran\OneDrive\Desktop\Screenshot_Organizer'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://127.0.0.1:8501. If occupied, append `--server.port 8502` and open that port.
The project configuration binds to localhost and disables Streamlit usage telemetry.
Do not expose this personal dashboard to a public network without authentication.

## Architecture

- `app.py`: five-page Streamlit interface, native layout/navigation controls, dialogs and
  a five-second Live Monitor fragment. OCR availability is cached for 60 seconds; service
  status and SQLite activity are read fresh. Other pages have a Refresh dashboard button.
- `src/dashboard_data.py`: UI adapters using existing metadata search/recent methods,
  read-only SQL aggregates and category filtering, safe local image decoding, service CLI
  controls and read-only Windows startup verification. No schema changes.
- `.streamlit/config.toml`: supported theme options, requested navy/indigo palette and local hosting.
- `manual_app.py`: previous optional manual approval workspace, retained with its existing
  tests. Run it separately with `python -m streamlit run manual_app.py`; normal automation
  does not require this workspace. The manual CLI remains available too.

Metrics include all successful copied/moved history records, including missing destination
files. Today uses this computer's local calendar date. Errors appear in activity and are
counted separately. Historical categories are displayed exactly as saved. Gallery limits
are adjustable to 120 newest matches; history displays the newest 200 matches. No records
are deleted by those display limits. Search uses the backend's all-words matching behavior.
Settings are intentionally read-only. Invalid configuration is reported, and the default
history location remains available. Raw OCR and diagnostic logs require explicit reveal.

## Verify each page

1. **Dashboard:** compare total/category counts against history; inspect the distribution
   chart and recent activity. Open the gallery using the quick-access button.
2. **Screenshot Gallery:** select a category, search, and open View screenshot. Check the
   image, title, source filename and destination. Reveal extracted text only when wanted.
   Missing or malformed images show a friendly placeholder with history preserved.
3. **Live Monitor:** confirm Running, the PID and Copy. The activity/status panel refreshes
   every five seconds. Start is disabled while active. Stop finishes the current item;
   use it only when you intend to pause automation. Logs are hidden until revealed.
4. **History & Search:** search a word from known OCR, apply a category, select a record,
   optionally show its image/excerpt/full OCR, and confirm its saved path and status.
5. **Settings:** check source/destination, OCR status and categories. Check Windows startup
   status on demand; this does not install, disable or alter a scheduled task.

## Verify independence

Read the service state before and after closing the browser or stopping only Streamlit
with Ctrl+C in its own terminal:

```powershell
.\.venv\Scripts\python.exe background.py status
```

Expect `active: true`, `state: running`, `mode: copy`, and the same watcher PID. Take a new
screenshot while Streamlit is closed, then reopen the dashboard and confirm its new history
entry. The original should still exist. Do not reprocess old screenshots for this check.

Run the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Dashboard tests cover empty data, actual totals/search, missing/corrupt images, invalid
settings, active/inactive services, explicit controls and no implicit watcher starts.
All previous manual-workspace tests remain in the suite against `manual_app.py`.

Rendered previews are kept locally in ignored `runtime/dashboard-previews/`; they contain
real personal history and should not be committed or published as portfolio examples.
