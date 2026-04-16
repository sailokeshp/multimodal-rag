import { useState } from 'react'
import { search } from '../../api'
import SearchForm from './SearchForm'
import ResultCard from './ResultCard'
import AnswerBox from './AnswerBox'

const QUERY_TYPE_LABEL = {
  hybrid: 'Hybrid', image: 'Image', text: 'Text', summary: 'Summary', compare: 'Compare',
}

export default function SearchView() {
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)
  const [results, setResults] = useState(null)  // null = no search yet

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

  const textHits  = results?.results?.filter(r => r.resultType === 'document_chunk') ?? []
  const imageHits = results?.results?.filter(r => r.resultType === 'image') ?? []

  return (
    <div className="space-y-5">
      <SearchForm onSearch={handleSearch} loading={loading} />

      {/* Error */}
      {error && (
        <div className="card p-4 border-red-300 bg-red-50 text-red-700 text-sm">
          ⚠ {error}
        </div>
      )}

      {/* No results yet */}
      {!results && !loading && !error && (
        <div className="text-center py-16 text-gray-400">
          <div className="text-5xl mb-3">🔍</div>
          <p className="text-lg font-medium text-gray-500">Search your documents</p>
          <p className="text-sm mt-1">Upload files first, then search with natural language.</p>
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="space-y-4">
          {/* Meta bar */}
          <div className="flex items-center gap-3 text-sm text-gray-500">
            <span>
              <span className="font-semibold text-gray-900">{results.results?.length ?? 0}</span> results
            </span>
            <span className="w-1 h-1 rounded-full bg-gray-300" />
            <span>Query type: <span className="font-medium text-blue-700">{QUERY_TYPE_LABEL[results.queryType] ?? results.queryType}</span></span>
            {results.results?.length === 0 && (
              <span className="text-amber-600">— try different keywords or upload more files</span>
            )}
          </div>

          {/* Grounded answer */}
          <AnswerBox answer={results.answer} queryType={QUERY_TYPE_LABEL[results.queryType]} />

          {/* Image hits grid */}
          {imageHits.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Images ({imageHits.length})
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 pl-7">
                {imageHits.map((r, i) => (
                  <ResultCard key={r.imageId ?? i} result={r} rank={i + 1} />
                ))}
              </div>
            </div>
          )}

          {/* Text hits */}
          {textHits.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Document Chunks ({textHits.length})
              </h3>
              <div className="space-y-3 pl-7">
                {textHits.map((r, i) => (
                  <ResultCard key={`${r.fileId}-${r.pageStart}-${i}`} result={r} rank={i + 1} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
