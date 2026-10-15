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

## Versione online (Render)

L'API e l'app web vengono pubblicate da un unico servizio (`Dockerfile`, `render.yaml`).
Fascicoli e documenti **non vanno sul server**: restano nel browser del PC dell'utente (IndexedDB), cifrati con AES-256-GCM.
La chiave master si ricava dalla passphrase con PBKDF2-SHA256 (600.000 iterazioni) e ogni fascicolo ha la sua chiave.
Sul server restano solo i dati commerciali: account, piani, crediti e consumi.

Render → New → Blueprint → repo `bpcall-proton/ius-italia-ai`. Imposta `IUS_DEMO_ADMIN_PASSWORD` e `IUS_DEMO_LAWYER_PASSWORD` (online le password di prova pubbliche non valgono).
Nota: i dati del browser sono legati a quel browser e a quel PC. Se cancelli i dati del sito o cambi computer, i fascicoli online non si possono recuperare.

## Motori AI: Ollama e "Mio AI"

- **Ollama** (`IUS_OLLAMA_URL`, predefinito `http://127.0.0.1:11434`; `IUS_OLLAMA_MODEL` è facoltativo e, se manca, si usa il primo modello installato). Ollama risulta attivo solo se risponde: nell'app desktop il caso resta sul PC.
- **Mio AI**: qualsiasi server compatibile con le API OpenAI (`IUS_CUSTOM_AI_URL`, ad es. `http://127.0.0.1:8000/v1`, poi `IUS_CUSTOM_AI_MODEL`, `IUS_CUSTOM_AI_KEY` facoltativa e `IUS_CUSTOM_AI_NAME`). Il modello si può cambiare anche da Admin → Modelli.
- Se l'indirizzo è locale (127.0.0.1/localhost), il consenso indica che i dati non escono dal PC. Se è remoto, viene trattato come fornitore esterno.
- Se la porta 8765 è occupata, l'app desktop usa automaticamente la prima porta libera.

## AI centralizzata e crediti

- Tutti gli account usano l'AI dell'amministratore: le chiavi OpenAI e l'indirizzo di Ollama stanno solo sul server centrale. Ogni richiesta scala i crediti dello studio in base ad Admin → Modelli (crediti ogni 1000 token).
- L'app desktop si collega al server centrale se è impostata la variabile GitHub `IUS_SERVER_URL` (in `ius-config.json`, scritto durante la build) oppure se esiste `%APPDATA%/IUS Italia AI/config.json` con `{ "serverUrl": "https://..." }`. Se non c'è, avvia il server demo locale.
- Ricarica: l'avvocato chiede i crediti dalla Dashboard, l'admin li approva in "Ricariche crediti" e i crediti vengono accreditati subito. Il pagamento si gestisce fuori dall'app finché non c'è un gateway.
