# IUS Italia AI

Piattaforma per avvocati e studi legali: dal fascicolo all'atto, con le proprie fonti, i propri documenti
e il pieno controllo del professionista. Versione **0.1 (MVP dimostrativo)**.

## Struttura
- `backend/` — FastAPI + SQLAlchemy/Alembic (SQLite in demo, PostgreSQL in produzione). Account, ruoli, sessioni revocabili,
  MFA TOTP obbligatoria per gli admin, piani e listini versionati, crediti con prenotazione atomica e idempotenza,
  registro consumi AI (solo metadati), orchestratore AI con streaming SSE e consenso esplicito per ogni invio.
- `desktop/` — Electron + React/TypeScript. Archivio locale cifrato (AES-256-GCM, chiave master da passphrase con scrypt,
  chiave distinta per fascicolo), import PDF con originale integro e SHA-256, editor atti, esportazione DOCX/PDF, stampa,
  analisi del caso, Smart Secretary (richiesta documenti e appuntamento), bozza da brief approvato, approvazione manuale,
  agenda del fascicolo, pannello di amministrazione separato.

## Account di prova
| Ruolo | Email | Password |
|---|---|---|
| Avvocato | avvocato@demo.ius | Demo-Avvocato-2026 |
| Admin (MFA al primo accesso) | admin@demo.ius | Demo-Admin-2026 |

## Avvio in sviluppo
```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/python backend/ius_server.py --data-dir ./data     # http://127.0.0.1:8765
cd desktop && npm ci && npm run desktop
```

## Windows 11
Il workflow **Build Windows** (manuale o tag `v*`) produce installer `.exe` e `.zip` con il server locale incluso.
Installare, avviare *IUS Italia AI*, accedere con l'account di prova, creare la passphrase dell'archivio.

## Stato reale della v0.1
| Funzione | Stato |
|---|---|
| Login, ruoli, sessioni revocabili, MFA admin | implementato e testato |
| Piani/prezzi versionati, crediti, limiti token, consumi | implementato e testato (dati demo) |
| Archivio cifrato, import PDF, editor, DOCX/PDF/stampa | implementato (vault testato) |
| Analisi caso e bozze | **SIMULATO**: motore a regole locale, dichiarato in interfaccia |
| OpenAI / DeepSeek | adapter pronti, **non configurati** (mancano le chiavi `IUS_OPENAI_API_KEY`, `IUS_DEEPSEEK_API_KEY`) |
| Fonti | catalogo ristretto di norme, sempre “da verificare sul testo vigente (Normattiva)”; nessuna sentenza |
| Normattiva/giurisprudenza live, Ollama, portale clienti, pagamenti, notifiche, multiutente | non ancora implementati |

L'amministrazione vede solo dati commerciali aggregati: fascicoli, documenti e bozze esistono solo sul computer
dell'avvocato e il server non ha endpoint per leggerli. Il controllo finale di ogni atto resta all'avvocato.
