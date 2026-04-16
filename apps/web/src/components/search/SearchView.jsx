import { useState } from 'react'
import { search, thumbnailUrl } from '../../api'
import SearchForm from './SearchForm'
import AnswerBox from './AnswerBox'

const QUERY_TYPE_LABEL = {
  hybrid: 'Hybrid', image: 'Image', text: 'Text', summary: 'Summary', compare: 'Compare',
}

function ScoreBadge({ score }) {
  const pct = Math.round(score * 100)
  const color = pct >= 70 ? 'text-green-700 bg-green-50' : pct >= 50 ? 'text-yellow-700 bg-yellow-50' : 'text-gray-600 bg-gray-100'
  return <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>{pct}%</span>
}

// ── Grid result card ────────────────────────────────────────────────────────
function GridResultCard({ result, rank }) {
  const isImg = result.resultType === 'image'
  const thumb = thumbnailUrl(result.thumbnailUrl)

  return (
    <div className="bg-white rounded-xl border border-gray-200 hover:shadow-md transition-shadow overflow-hidden flex flex-col">
      <div className="relative bg-gray-50 h-40 flex items-center justify-center overflow-hidden">
        {thumb ? (
          <img src={thumb} alt={result.fileName} className="w-full h-full object-cover"
            onError={e => { e.target.style.display = 'none' }} />
        ) : (
          <span className="text-4xl">{isImg ? '🖼' : '📄'}</span>
        )}
        <span className="absolute top-2 left-2 bg-black/50 text-white text-xs w-5 h-5 rounded-full flex items-center justify-center font-mono">
          {rank}
        </span>
        <div className="absolute top-2 right-2"><ScoreBadge score={result.score} /></div>
      </div>
      <div className="p-3">
        <p className="text-xs font-medium text-gray-900 truncate mb-1">{result.fileName}</p>
        {isImg
          ? result.caption && <p className="text-xs text-gray-500 line-clamp-2">{result.caption}</p>
          : <p className="text-xs text-gray-600 line-clamp-3 leading-relaxed">{result.snippet}</p>
        }
      </div>
    </div>
  )
}

// ── List result row ──────────────────────────────────────────────────────────
function ListResultRow({ result, rank }) {
  const isImg = result.resultType === 'image'
  const thumb = thumbnailUrl(result.thumbnailUrl)
  const page = result.pageStart != null
    ? result.pageEnd != null && result.pageEnd !== result.pageStart
      ? `Pages ${result.pageStart}–${result.pageEnd}` : `Page ${result.pageStart}`
    : null

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-3 hover:shadow-sm transition-shadow flex gap-3">
      <span className="text-xs text-gray-400 font-mono w-4 flex-shrink-0 mt-0.5">{rank}</span>
      <div className="w-12 h-12 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0 flex items-center justify-center">
        {thumb
          ? <img src={thumb} alt="" className="w-full h-full object-cover" onError={e => { e.target.style.display = 'none' }} />
          : <span className="text-2xl">{isImg ? '🖼' : '📄'}</span>
        }
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium text-blue-700 truncate">{result.fileName}</span>
          {page && <span className="text-xs text-gray-400 flex-shrink-0">{page}</span>}
          <ScoreBadge score={result.score} />
        </div>
        {isImg
          ? result.caption && <p className="text-xs text-gray-600 line-clamp-2">{result.caption}</p>
          : <p className="text-sm text-gray-700 line-clamp-2 leading-relaxed">{result.snippet}</p>
        }
      </div>
    </div>
  )
}

export default function SearchView() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [results, setResults] = useState(null)
  const [view, setView] = useState('grid')

  const handleSearch = async params => {
    setLoading(true)
    setError(null)
    try {
      const data = await search(params)
      setResults(data)
    } catch (err) {
      setError(err.message)
      setResults(null)
    } finally {
      setLoading(false)
    }
  }

  const allResults = results?.results ?? []

  return (
    <div className="space-y-5">
      <SearchForm onSearch={handleSearch} loading={loading} />

      {error && (
        <div className="rounded-xl p-4 border border-red-300 bg-red-50 text-red-700 text-sm">⚠ {error}</div>
      )}

      {!results && !loading && !error && (
        <div className="text-center py-20 text-gray-400">
          <div className="text-5xl mb-3">🔍</div>
          <p className="text-lg font-medium text-gray-500">Search your assets</p>
          <p className="text-sm mt-1">Ask anything — hybrid text + image search</p>
        </div>
      )}

      {results && (
        <div className="space-y-4">
          {/* Meta bar */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span><span className="font-semibold text-gray-900">{allResults.length}</span> results</span>
              <span className="w-1 h-1 rounded-full bg-gray-300" />
              <span>Query type: <span className="font-medium text-blue-700">{QUERY_TYPE_LABEL[results.queryType] ?? results.queryType}</span></span>
              {allResults.length === 0 && <span className="text-amber-600">— try different keywords</span>}
            </div>
            {/* View toggle */}
            <div className="flex bg-gray-100 rounded-lg p-0.5">
              {[['grid', '⊞'], ['list', '≡']].map(([v, icon]) => (
                <button key={v} onClick={() => setView(v)}
                  className={`px-3 py-1.5 rounded-md text-sm transition-all ${view === v ? 'bg-white shadow-sm text-blue-700 font-medium' : 'text-gray-500 hover:text-gray-700'}`}>
                  {icon}
                </button>
              ))}
            </div>
          </div>

          {/* Grounded answer */}
          <AnswerBox answer={results.answer} queryType={QUERY_TYPE_LABEL[results.queryType]} />

          {/* Results */}
          {allResults.length > 0 && (
            view === 'grid' ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {allResults.map((r, i) => (
                  <GridResultCard key={r.imageId ?? `${r.fileId}-${i}`} result={r} rank={i + 1} />
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {allResults.map((r, i) => (
                  <ListResultRow key={r.imageId ?? `${r.fileId}-${i}`} result={r} rank={i + 1} />
                ))}
              </div>
            )
          )}
        </div>
      )}
    </div>
  )
}
