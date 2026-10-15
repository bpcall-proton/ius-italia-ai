import { AlignmentType, Document, HeadingLevel, Packer, Paragraph, TextRun } from 'docx'

type Style = { bold?: boolean; italics?: boolean; underline?: object }

function runs(node: Node, style: Style = {}): TextRun[] {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent ?? ''
    return text ? [new TextRun({ text, ...style })] : []
  }
  if (!(node instanceof HTMLElement)) return []
  const tag = node.tagName
  if (tag === 'BR') return [new TextRun({ break: 1 })]
  const s = { ...style }
  if (tag === 'B' || tag === 'STRONG') s.bold = true
  if (tag === 'I' || tag === 'EM') s.italics = true
  if (tag === 'U') s.underline = {}
  return Array.from(node.childNodes).flatMap((c) => runs(c, s))
}

function align(el: HTMLElement) {
  const a = el.style.textAlign
  if (a === 'center') return AlignmentType.CENTER
  if (a === 'right') return AlignmentType.RIGHT
  if (a === 'justify') return AlignmentType.JUSTIFIED
  return undefined
}

export function htmlToParagraphs(html: string): Paragraph[] {
  const root = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html').body.firstElementChild as HTMLElement
  const out: Paragraph[] = []
  const walk = (el: HTMLElement) => {
    for (const child of Array.from(el.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) {
        if (child.textContent?.trim()) out.push(new Paragraph({ children: runs(child) }))
        continue
      }
      if (!(child instanceof HTMLElement)) continue
      const tag = child.tagName
      if (tag === 'UL' || tag === 'OL') {
        Array.from(child.children).forEach((li, i) =>
          out.push(
            new Paragraph({
              children: [new TextRun(tag === 'OL' ? `${i + 1}. ` : '• '), ...runs(li)],
              indent: { left: 360 },
            }),
          ),
        )
      } else if (tag === 'DIV' || tag === 'SECTION') walk(child)
      else {
        const heading =
          tag === 'H1' ? HeadingLevel.HEADING_1 : tag === 'H2' ? HeadingLevel.HEADING_2 : tag === 'H3' ? HeadingLevel.HEADING_3 : undefined
        out.push(new Paragraph({ children: runs(child), heading, alignment: align(child), spacing: { after: 120 } }))
      }
    }
  }
  walk(root)
  return out
}

export async function htmlToDocx(html: string, title: string): Promise<Uint8Array> {
  const doc = new Document({
    creator: 'IUS Italia AI',
    title,
    styles: { default: { document: { run: { font: 'Times New Roman', size: 24 } } } },
    sections: [{ children: htmlToParagraphs(html) }],
  })
  return new Uint8Array(await (await Packer.toBlob(doc)).arrayBuffer())
}

export function printableHtml(html: string, title: string): string {
  const esc = title.replace(/[<>&"]/g, (c) => `&#${c.charCodeAt(0)};`)
  return `<!doctype html><html lang="it"><head><meta charset="utf-8"><title>${esc}</title><style>
@page{size:A4;margin:2.5cm 2cm}body{font-family:'Times New Roman',serif;font-size:12pt;line-height:1.5;color:#000}
h1{font-size:15pt;text-align:center}h2{font-size:13pt}p{margin:0 0 8pt;text-align:justify}</style></head><body>${html}</body></html>`
}
