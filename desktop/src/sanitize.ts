const ALLOWED = new Set(['P', 'H1', 'H2', 'H3', 'STRONG', 'B', 'EM', 'I', 'U', 'UL', 'OL', 'LI', 'BR', 'DIV', 'SPAN', 'BLOCKQUOTE'])
const ALIGN = /^(left|right|center|justify)$/

/** Riduce l'HTML (anche quello generato dall'AI) a un sottoinsieme sicuro per l'editor. */
export function sanitizeHtml(html: string): string {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html')
  const clean = (el: Element) => {
    for (const child of Array.from(el.children)) {
      if (!ALLOWED.has(child.tagName)) {
        if (['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'LINK', 'META'].includes(child.tagName)) child.remove()
        else child.replaceWith(...Array.from(child.childNodes))
        continue
      }
      const align = (child as HTMLElement).style?.textAlign
      for (const attr of Array.from(child.attributes)) child.removeAttribute(attr.name)
      if (align && ALIGN.test(align)) (child as HTMLElement).style.textAlign = align
      clean(child)
    }
  }
  const root = doc.body.firstElementChild!
  let before = ''
  while (before !== root.innerHTML) {
    before = root.innerHTML
    clean(root)
  }
  return root.innerHTML
}
