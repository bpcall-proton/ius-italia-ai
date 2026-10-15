# AGENTS

- Backend (`backend/`, Python 3.10+): `python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt`;
  da `backend/`: `../.venv/bin/ruff check . && ../.venv/bin/ruff format --check . && ../.venv/bin/python -m pytest -q`.
- Desktop (`desktop/`, Node 22): `npm ci`, `npm run lint`, `npm test`, `npx tsc -b && npx vite build`.
- Avvio dev: `python backend/ius_server.py --data-dir ./data` poi `cd desktop && npm run desktop`.
- Nuove migrazioni: da `backend/`, `../.venv/bin/alembic -x ... revision --autogenerate` (vedi `app/migrate.py`).
- Regole: nessuna chiave API nel codice o nel frontend; il server non deve mai salvare testo dei fascicoli o dei prompt;
  la modalità `simulation` va sempre dichiarata come tale; nessuna fonte o sentenza inventata.
