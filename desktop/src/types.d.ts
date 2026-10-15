export interface CaseSummary {
  id: string
  title: string
  client: string
  matter: string
  createdAt: string
  updatedAt: string
  documents: number
  drafts: number
  agenda: number
}
export interface DocMeta {
  id: string
  name: string
  mime: string
  size: number
  sha256: string
  importedAt: string
}
export interface Draft {
  id: string
  title: string
  html: string
  status: 'bozza' | 'approvata'
  source: 'manuale' | 'ai-simulazione' | 'ai'
  updatedAt: string
  approvedAt?: string
}
export interface AgendaItem {
  id: string
  kind: 'appuntamento' | 'scadenza' | 'attività'
  title: string
  date: string
  note?: string
  confirmed: boolean
}
export interface SavedAnalysis {
  id: string
  at: string
  provider: string
  simulated: boolean
  data: Analysis
}
export interface CaseData {
  id: string
  title: string
  client: string
  matter: string
  notes: string
  createdAt: string
  updatedAt: string
  documents: DocMeta[]
  drafts: Draft[]
  analyses: SavedAnalysis[]
  agenda: AgendaItem[]
}
export interface Norm {
  id: string
  citation: string
  heading: string
  url: string
  status: string
  verified_text: boolean
}
export interface Analysis {
  summary: string
  conclusion_status: string
  facts: { declared: unknown[]; documented: unknown[]; controversial: unknown[] }
  missing_information: unknown[]
  legal_questions: unknown[]
  candidate_norms: Norm[]
  case_law: unknown[]
  case_law_note: string
  alternative_interpretations: unknown[]
  favorable: unknown[]
  unfavorable: unknown[]
  evidence_issues: unknown[]
  risks: unknown[]
  scenarios: unknown[]
  next_actions: unknown[]
  citation_check: unknown[]
  secretary: {
    document_request: { recipient: string; items: string[]; due_days: number }
    appointment: { type: string; duration_min: number; reason: string; availability: string }
  }
  draft_brief: Brief
}
export interface Brief {
  doc_type: string
  subject: string
  recipient?: string
  sender?: string
  approved_facts: string[]
  requests: string[]
  approved_norm_ids: string[]
  due_days?: number
}
export interface DraftResult {
  title: string
  html: string
  used_facts: string[]
  used_norm_ids: string[]
  missing_fields: string[]
  notice: string
}

interface IusBridge {
  web?: boolean
  backendUrl: string
  vault: {
    status(): Promise<{ exists: boolean; unlocked: boolean }>
    create(p: string): Promise<{ exists: boolean; unlocked: boolean }>
    unlock(p: string): Promise<{ exists: boolean; unlocked: boolean }>
    lock(): Promise<{ exists: boolean; unlocked: boolean }>
  }
  cases: {
    list(): Promise<CaseSummary[]>
    create(input: { title: string; client: string; matter: string }): Promise<CaseData>
    get(id: string): Promise<CaseData>
    update(id: string, patch: Partial<CaseData>): Promise<CaseData>
  }
  docs: {
    importPdf(caseId: string): Promise<DocMeta[]>
    read(caseId: string, docId: string): Promise<{ doc: DocMeta; data: Uint8Array }>
    saveCopy(caseId: string, docId: string): Promise<string | null>
  }
  exportDocx(bytes: Uint8Array, name: string): Promise<string | null>
  exportPdf(html: string, name: string): Promise<string | null>
  print(html: string): Promise<string>
}

declare global {
  interface Window {
    ius?: IusBridge
  }
}
