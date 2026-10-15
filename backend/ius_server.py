"""Avvio del backend (anche come eseguibile PyInstaller per la modalità demo locale)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="IUS Italia AI — server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=None, help="Cartella per database demo e segreto JWT")
    args = parser.parse_args()
    log_dir = Path.cwd()
    os.environ.setdefault("IUS_LOCAL_MODE", "1")
    if args.data_dir:
        data = Path(args.data_dir)
        data.mkdir(parents=True, exist_ok=True)
        log_dir = data
        os.environ.setdefault("IUS_DATA_DIR", str(data))
        os.environ.setdefault("IUS_DATABASE_URL", f"sqlite:///{(data / 'ius-demo.db').as_posix()}")
    # Con PyInstaller --noconsole stdout/stderr sono None e uvicorn non riesce a configurare il logging.
    if sys.stdout is None or sys.stderr is None:
        log = open(log_dir / "ius-server.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log

    import uvicorn

    from app.main import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
