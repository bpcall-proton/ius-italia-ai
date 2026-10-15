"""IUS Legal Sources — catalogo locale minimo delle fonti (v0.1).

Contiene soltanto rubrica e collegamento URN a Normattiva: il testo vigente NON è incluso
e deve essere verificato sulla fonte ufficiale. Nessuna giurisprudenza è disponibile in v0.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NORMATTIVA = "https://www.normattiva.it/uri-res/N2Ls?"
CP_URN = "urn:nir:stato:regio.decreto:1930-10-19;1398"
CC_URN = "urn:nir:stato:regio.decreto:1942-03-16;262"

VERIFY_STATUS = "da verificare sul testo vigente (Normattiva)"


@dataclass(frozen=True)
class Source:
    id: str
    code: str
    article: str
    heading: str
    urn: str

    @property
    def citation(self) -> str:
        return f"art. {self.article} {self.code}"

    @property
    def url(self) -> str:
        return f"{NORMATTIVA}{self.urn}"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "citation": self.citation,
            "heading": self.heading,
            "url": self.url,
            "status": VERIFY_STATUS,
            "verified_text": False,
        }


def _cp(article: str, heading: str) -> Source:
    return Source(f"cp-{article}", "c.p.", article, heading, f"{CP_URN}~art{article}")


def _cc(article: str, heading: str) -> Source:
    return Source(f"cc-{article}", "c.c.", article, heading, f"{CC_URN}~art{article}")


CATALOG: dict[str, Source] = {
    s.id: s
    for s in [
        _cp("494", "Sostituzione di persona"),
        _cp("483", "Falsità ideologica commessa dal privato in atto pubblico"),
        _cp("640", "Truffa"),
        _cp("595", "Diffamazione"),
        _cp("157", "Prescrizione. Tempo necessario a prescrivere"),
        _cp("158", "Decorrenza del termine della prescrizione"),
        _cp("159", "Sospensione del corso della prescrizione"),
        _cp("160", "Interruzione del corso della prescrizione"),
        _cp("161", "Effetti della sospensione e della interruzione"),
        _cc("1218", "Responsabilità del debitore"),
        _cc("1453", "Risolubilità del contratto per inadempimento"),
        _cc("2043", "Risarcimento per fatto illecito"),
        _cc("2697", "Onere della prova"),
    ]
}


@dataclass
class Issue:
    id: str
    title: str
    sources: list[str]
    priority: int
    why: str
    triggers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IssueRule:
    id: str
    title: str
    patterns: tuple[str, ...]
    sources: tuple[str, ...]
    priority: int
    why: str


RULES: tuple[IssueRule, ...] = (
    IssueRule(
        "sostituzione_persona",
        "Possibile sostituzione di persona / uso dell'identità altrui",
        (
            r"\ba nome (della|del|di)\b",
            r"sostituzione di persona",
            r"spacciandosi",
            r"identit[àa] altrui",
            r"falsa identit",
            r"intestat\w* (a|alla|al) ",
            r"usurpa",
        ),
        ("cp-494",),
        10,
        "La descrizione riferisce l'uso del nome o dell'identità di un'altra persona.",
    ),
    IssueRule(
        "dichiarazioni_pubblico_ufficiale",
        "Eventuali dichiarazioni non veritiere rese a un ufficio pubblico",
        (r"partita iva", r"agenzia delle entrate", r"dichiarazion\w+ (falsa|non veritiera)", r"pubblico ufficiale"),
        ("cp-483",),
        5,
        "L'apertura di posizioni fiscali comporta dichiarazioni a un ufficio pubblico: valutare se e quali.",
    ),
    IssueRule(
        "prescrizione",
        "Prescrizione del reato: termini, decorrenza, sospensione e interruzione",
        (r"\b(19|20)\d{2}\b", r"prescri", r"anni fa", r"denunc", r"querel"),
        ("cp-157", "cp-158", "cp-159", "cp-160", "cp-161"),
        8,
        "Tra i fatti e la denuncia è trascorso tempo: la prescrizione va verificata con i dati completi.",
    ),
    IssueRule(
        "truffa",
        "Possibile induzione in errore con profitto e danno",
        (r"\btruff", r"raggir", r"artifiz", r"ingann"),
        ("cp-640",),
        6,
        "La descrizione richiama condotte ingannatorie con possibile profitto.",
    ),
    IssueRule(
        "diffamazione",
        "Possibile lesione della reputazione",
        (r"diffam", r"offes\w+ (la|alla) reputazione", r"post offensiv"),
        ("cp-595",),
        6,
        "La descrizione richiama comunicazioni lesive della reputazione.",
    ),
    IssueRule(
        "inadempimento",
        "Inadempimento contrattuale e rimedi",
        (r"inadempi", r"non ha pagato", r"mancato pagamento", r"contratto", r"risoluzione"),
        ("cc-1218", "cc-1453"),
        6,
        "La descrizione richiama obbligazioni contrattuali non adempiute.",
    ),
    IssueRule(
        "danno",
        "Risarcimento del danno",
        (r"\bdann[oi]\b", r"risarc"),
        ("cc-2043",),
        4,
        "La descrizione richiama un danno di cui chiedere il ristoro.",
    ),
    IssueRule(
        "prova",
        "Prova dei fatti e onere probatorio",
        (r"document", r"firmat", r"email", r"comunicazion", r"testimon", r"consenso telefonico", r"telefon"),
        ("cc-2697",),
        3,
        "Alcuni fatti sono documentati, altri solo dichiarati: occorre valutare cosa si può provare.",
    ),
)


def detect_issues(text: str) -> list[Issue]:
    low = text.lower()
    found: list[Issue] = []
    for rule in RULES:
        hits = [p for p in rule.patterns if re.search(p, low)]
        if not hits:
            continue
        if rule.id == "prescrizione" and not any(re.search(p, low) for p in (r"prescri", r"denunc", r"querel")):
            continue
        if rule.id == "prova" and not found:
            continue
        found.append(Issue(rule.id, rule.title, list(rule.sources), rule.priority, rule.why, hits))
    penal = any(i.id in {"sostituzione_persona", "truffa", "diffamazione"} for i in found)
    if not penal:
        found = [i for i in found if i.id not in {"prescrizione", "dichiarazioni_pubblico_ufficiale"}]
    found.sort(key=lambda i: -i.priority)
    return found


def sources_for(issues: list[Issue]) -> list[Source]:
    seen: list[str] = []
    for issue in issues:
        for sid in issue.sources:
            if sid not in seen:
                seen.append(sid)
    return [CATALOG[s] for s in seen]


def validate_citations(text: str, allowed_ids: list[str]) -> list[dict]:
    """Segnala ogni 'art. N c.p./c.c.' citato che non è fra le fonti recuperate e approvate."""
    allowed = {CATALOG[i].citation for i in allowed_ids if i in CATALOG}
    problems = []
    for m in re.finditer(r"art(?:icolo|\.)\s*(\d+(?:-\w+)?)\s*(c\.p\.|c\.c\.|cod\. pen\.|cod\. civ\.)", text, re.I):
        raw = m.group(2).lower()
        code = "c.p." if raw.startswith(("c.p", "cod. pen")) else "c.c."
        cit = f"art. {m.group(1)} {code}"
        if cit not in allowed:
            problems.append({"citation": cit, "problem": "Fonte non recuperata dal catalogo: non verificata"})
    return problems
