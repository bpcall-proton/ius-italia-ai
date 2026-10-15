"""Motore dimostrativo a regole (provider "simulation").

NON è un modello AI: estrae frasi dalla descrizione e applica regole fisse sul catalogo
locale delle fonti. Serve a far funzionare il flusso end-to-end senza chiavi API.
"""

from __future__ import annotations

import html
import re

from .legal_sources import CATALOG, detect_issues, sources_for

DOC_HINT = re.compile(r"document|firmat|email|e-mail|pec|comunicazion|contratt|fattur|ricevut|estratt", re.I)
CLAIM_HINT = re.compile(r"sostien|sostenendo|afferma|dichiara|riferisce|consenso|a suo dire|secondo", re.I)
YEAR = re.compile(r"\b(19|20)\d{2}\b")


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def analyze(description: str) -> dict:
    sents = sentences(description)
    issues = detect_issues(description)
    sources = sources_for(issues)
    years = sorted({m.group(0) for m in YEAR.finditer(description)})
    issue_ids = {i.id for i in issues}

    documented = [s for s in sents if DOC_HINT.search(s)]
    controversial = [s for s in sents if CLAIM_HINT.search(s)]
    declared = [s for s in sents if s not in documented]

    missing = [
        "Date esatte di ciascun evento (giorno, mese, anno) e relativa fonte documentale.",
        "Copia dei documenti citati e indicazione di chi li ha firmati.",
    ]
    if "prescrizione" in issue_ids:
        missing += [
            "Data di consumazione del fatto e data dell'eventuale ultima condotta.",
            "Data della denuncia/querela e di eventuali atti interruttivi o cause di sospensione.",
            "Qualificazione giuridica e pena edittale applicabile, necessarie per il calcolo dei termini.",
        ]
    if controversial:
        missing.append("Elementi di riscontro sulle circostanze solo dichiarate (es. il consenso riferito).")

    questions = [
        {
            "issue": i.title,
            "why": i.why,
            "sources": [CATALOG[s].citation for s in i.sources],
        }
        for i in issues
    ]

    favorable, unfavorable, risks, scenarios, activities = [], [], [], [], []
    if "sostituzione_persona" in issue_ids:
        favorable.append("Esistono documenti firmati che possono chiarire chi ha agito e a nome di chi.")
        unfavorable.append(
            "La controparte sostiene un consenso: se provato, potrebbe incidere sulla rilevanza penale della condotta."
        )
        scenarios.append(
            "SE il consenso non risulta e l'uso del nome è documentato, ALLORA va valutata la fattispecie di "
            "sostituzione di persona (art. 494 c.p.), da verificare sul testo vigente."
        )
        scenarios.append(
            "SE emerge un consenso effettivo e documentabile, ALLORA la ricostruzione accusatoria si indebolisce "
            "e vanno valutate altre qualificazioni o profili civilistici."
        )
    if "prescrizione" in issue_ids:
        risks.append(
            "Possibile decorso del termine di prescrizione: NON è possibile stabilire se il reato sia prescritto "
            "senza date esatte, qualificazione, pena edittale e atti interruttivi/sospensivi."
        )
        activities.append(
            "Ricostruire una cronologia documentata per il calcolo della prescrizione (artt. 157–161 c.p.)."
        )
    if "inadempimento" in issue_ids:
        activities.append("Raccogliere contratto, corrispondenza e prova dei pagamenti per valutare l'inadempimento.")
    risks.append("Le valutazioni sono preliminari e basate solo sulla descrizione fornita.")
    activities += [
        "Colloquio con il cliente per chiarire i fatti mancanti.",
        "Acquisire i documenti indicati nella richiesta documentale.",
        "Verificare il testo vigente delle norme candidate su Normattiva prima di ogni utilizzo.",
    ]

    doc_requests = [
        "Documenti firmati relativi ai fatti descritti",
        "Comunicazioni (email, messaggi, PEC) con le date di invio",
        "Documento d'identità e codice fiscale del cliente",
    ]
    if "dichiarazioni_pubblico_ufficiale" in issue_ids:
        doc_requests.append("Visura e documentazione di apertura della posizione fiscale (es. partita IVA)")
    if "prescrizione" in issue_ids:
        doc_requests.append("Copia della denuncia/querela con data di deposito")

    summary_bits = [i.title for i in issues[:3]] or ["Nessuna questione riconosciuta dal motore a regole"]
    return {
        "summary": "Questioni da approfondire: " + "; ".join(summary_bits) + ".",
        "conclusion_status": "preliminare — nessuna conclusione certa",
        "years_mentioned": years,
        "facts": {"declared": declared, "documented": documented, "controversial": controversial},
        "missing_information": missing,
        "legal_questions": questions,
        "candidate_norms": [s.as_dict() for s in sources],
        "case_law": [],
        "case_law_note": "Nessuna giurisprudenza verificata disponibile in questa versione: non viene citata alcuna sentenza.",
        "alternative_interpretations": [s for s in scenarios[1:]] or [],
        "favorable": favorable,
        "unfavorable": unfavorable,
        "evidence_issues": [
            "Distinguere fatti documentati da fatti solo dichiarati.",
            "Valutare l'onere della prova sulle circostanze contestate.",
        ],
        "risks": risks,
        "scenarios": scenarios,
        "next_actions": activities,
        "secretary": {
            "document_request": {"recipient": "Cliente (da confermare)", "items": doc_requests, "due_days": 10},
            "appointment": {
                "type": "colloquio cliente",
                "duration_min": 60,
                "reason": "Chiarire fatti mancanti e consegnare i documenti",
                "availability": "da verificare in agenda",
            },
        },
        "draft_brief": {
            "doc_type": "richiesta_documenti",
            "subject": "Richiesta di documentazione",
            "approved_facts": [],
            "requests": doc_requests,
            "approved_norm_ids": [s.id for s in sources],
            "due_days": 10,
        },
    }


DOC_TYPES = {
    "richiesta_documenti": "Richiesta di documentazione",
    "diffida": "Diffida",
    "lettera": "Lettera",
    "parere": "Parere preliminare",
}


def _p(text: str) -> str:
    return f"<p>{html.escape(text)}</p>"


def draft(brief: dict) -> dict:
    """Bozza costruita SOLO dal DraftBrief approvato: niente fatti o norme aggiuntivi."""
    doc_type = brief.get("doc_type") or "lettera"
    title = DOC_TYPES.get(doc_type, "Lettera")
    sender = brief.get("sender") or "[DA COMPLETARE: avvocato mittente]"
    recipient = brief.get("recipient") or "[DA COMPLETARE: destinatario]"
    subject = brief.get("subject") or title
    facts = [f for f in brief.get("approved_facts") or [] if f.strip()]
    requests = [r for r in brief.get("requests") or [] if r.strip()]
    norms = [CATALOG[n] for n in brief.get("approved_norm_ids") or [] if n in CATALOG]
    due = brief.get("due_days")
    missing = []
    if not brief.get("sender"):
        missing.append("mittente")
    if not brief.get("recipient"):
        missing.append("destinatario")

    out = [
        f"<p><strong>{html.escape(sender)}</strong></p>",
        f"<p>Spett.le {html.escape(recipient)}</p>",
        "<p>[DA COMPLETARE: luogo], [DA COMPLETARE: data]</p>",
        f"<h2>Oggetto: {html.escape(subject)}</h2>",
        _p("Egregio/Gentile,"),
    ]
    if facts:
        out.append(_p("con riferimento alla pratica in oggetto, si richiamano i seguenti fatti:"))
        out.append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>")
    if requests:
        verb = "si invita a" if doc_type == "diffida" else "si chiede cortesemente di"
        out.append(_p(f"{verb[0].upper()}{verb[1:]} trasmettere / provvedere a quanto segue:"))
        out.append("<ol>" + "".join(f"<li>{html.escape(r)}</li>" for r in requests) + "</ol>")
    if due:
        out.append(_p(f"entro {int(due)} giorni dal ricevimento della presente."))
    if norms:
        refs = ", ".join(f"{n.citation} ({n.heading})" for n in norms)
        out.append(_p(f"Riferimenti normativi da verificare prima dell'invio: {refs}."))
    out += [_p("Distinti saluti."), f"<p>{html.escape(sender)}</p>"]
    return {
        "title": f"{title} — {subject}",
        "html": "\n".join(out),
        "used_facts": facts,
        "used_norm_ids": [n.id for n in norms],
        "missing_fields": missing,
        "notice": "Bozza da rivedere: nessun fatto o norma oltre a quelli approvati nel brief.",
    }
