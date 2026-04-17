/**
 * AnswerBox — renders the grounded LLM answer with basic markdown support.
 *
 * Renders:
 *  **bold**          → <strong>
 *  *italic*          → <em>
 *  `code`            → <code>
 *  - bullet / * bullet  → <ul><li>
 *  Sources:\n- …     → styled citation list
 *  Plain paragraphs  → <p>
 */

function parseMarkdown(text) {
  // Split on the Sources: block first so citations get special styling
  const [body, sourcesRaw] = text.split(/\n\n?Sources:\n/i)
  const sources = sourcesRaw
    ? sourcesRaw.split('\n').map(l => l.replace(/^[-*]\s*/, '').trim()).filter(Boolean)
    : []

  return { body: body?.trim() || text, sources }
}

function renderInline(text) {
  // Bold → strong, italic → em, backtick → code
  const parts = []
  let remaining = text
  let key = 0

  const patterns = [
    { re: /\*\*(.+?)\*\*/,  Tag: 'strong' },
    { re: /\*(.+?)\*/,      Tag: 'em'     },
    { re: /`([^`]+)`/,      Tag: 'code'   },
  ]

  outer: while (remaining.length) {
    let earliest = { index: Infinity, match: null, Tag: null }
    for (const { re, Tag } of patterns) {
      const m = re.exec(remaining)
      if (m && m.index < earliest.index) earliest = { index: m.index, match: m, Tag }
    }

    if (!earliest.match) {
      parts.push(<span key={key++}>{remaining}</span>)
      break
    }

    if (earliest.index > 0) {
      parts.push(<span key={key++}>{remaining.slice(0, earliest.index)}</span>)
    }
    const { match, Tag } = earliest
    parts.push(
      <Tag key={key++} className={Tag === 'code' ? 'bg-gray-100 text-red-700 px-1 rounded font-mono text-xs' : ''}>
        {match[1]}
      </Tag>
    )
    remaining = remaining.slice(earliest.index + match[0].length)
  }
  return parts
}

function renderBody(text) {
  const lines = text.split('\n')
  const elements = []
  let listItems = []
  let key = 0

  const flushList = () => {
    if (!listItems.length) return
    elements.push(
      <ul key={key++} className="list-disc list-inside space-y-1 my-2 pl-2">
        {listItems.map((item, i) => (
          <li key={i} className="text-gray-800 text-sm leading-relaxed">
            {renderInline(item)}
          </li>
        ))}
      </ul>
    )
    listItems = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      continue
    }
    if (/^[-*]\s+/.test(trimmed)) {
      listItems.push(trimmed.replace(/^[-*]\s+/, ''))
    } else {
      flushList()
      elements.push(
        <p key={key++} className="text-gray-800 text-sm leading-relaxed mb-2">
          {renderInline(trimmed)}
        </p>
      )
    }
  }
  flushList()
  return elements
}

export default function AnswerBox({ answer, queryType }) {
  if (!answer) return null

  const { body, sources } = parseMarkdown(answer)

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-5 py-3 border-b border-blue-200 bg-blue-100/60">
        <span className="text-blue-600 text-base">✨</span>
        <span className="text-sm font-semibold text-blue-800">Grounded Answer</span>
        <span className="ml-1 px-2 py-0.5 bg-blue-200 text-blue-700 rounded-full text-xs font-medium">
          {queryType}
        </span>
      </div>

      {/* Answer body */}
      <div className="px-5 py-4">
        {renderBody(body)}
      </div>

      {/* Citations */}
      {sources.length > 0 && (
        <div className="px-5 py-3 border-t border-blue-200 bg-blue-100/40">
          <p className="text-xs font-semibold text-blue-700 mb-2">Sources</p>
          <ul className="space-y-1">
            {sources.map((src, i) => (
              <li key={i} className="text-xs text-blue-800 flex items-start gap-1.5">
                <span className="text-blue-400 mt-0.5">▸</span>
                <span>{src}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
