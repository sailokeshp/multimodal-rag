import { useState } from 'react'

export default function SearchForm({ onSearch, loading }) {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(8)
  const [includeAnswer, setIncludeAnswer] = useState(true)

  const submit = e => {
    e.preventDefault()
    const q = query.trim()
    if (!q || loading) return
    onSearch({ query: q, topK, includeAnswer })
  }

  return (
    <form onSubmit={submit} className="card p-5 space-y-4">
      {/* Query input */}
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Ask anything about your documents or images…"
          className="flex-1 px-4 py-2.5 rounded-lg border border-gray-300 text-sm
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                     placeholder-gray-400"
          disabled={loading}
          autoFocus
        />
        <button type="submit" disabled={!query.trim() || loading} className="btn-primary px-6">
          {loading
            ? <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            : '🔍 Search'}
        </button>
      </div>

      {/* Options row */}
      <div className="flex flex-wrap items-center gap-5">
        {/* Top-K slider */}
        <label className="flex items-center gap-3 text-sm text-gray-600">
          <span className="shrink-0">Results:</span>
          <input
            type="range"
            min={1} max={20} step={1}
            value={topK}
            onChange={e => setTopK(Number(e.target.value))}
            className="w-28 accent-blue-600"
          />
          <span className="w-5 text-center font-semibold text-gray-800">{topK}</span>
        </label>

        {/* Answer toggle */}
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
          <span className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                            cursor-pointer"
                style={{ background: includeAnswer ? '#3b82f6' : '#d1d5db' }}
                onClick={() => setIncludeAnswer(v => !v)}
          >
            <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform
                             ${includeAnswer ? 'translate-x-4' : 'translate-x-0.5'}`} />
          </span>
          Generate answer
          <span className="text-xs text-gray-400">(Gemini API)</span>
        </label>
      </div>
    </form>
  )
}
