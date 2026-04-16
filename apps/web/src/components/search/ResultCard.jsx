import { thumbnailUrl } from '../../api'

function ScoreBadge({ score }) {
  const pct = Math.round(score * 100)
  const color = pct >= 70 ? 'text-green-700 bg-green-50' : pct >= 50 ? 'text-yellow-700 bg-yellow-50' : 'text-gray-600 bg-gray-100'
  return (
    <span className={`ml-auto shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
      {pct}%
    </span>
  )
}

function TextChunkCard({ result }) {
  const page = result.pageStart != null
    ? result.pageEnd != null && result.pageEnd !== result.pageStart
      ? `Pages ${result.pageStart}–${result.pageEnd}`
      : `Page ${result.pageStart}`
    : null

  return (
    <div className="card p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-2 mb-2">
        <span className="text-gray-400 text-xs mt-0.5">📄</span>
        <div className="flex-1 min-w-0">
          <span className="text-xs font-medium text-blue-700 truncate block">{result.fileName}</span>
          {page && <span className="text-xs text-gray-400">{page}</span>}
        </div>
        <ScoreBadge score={result.score} />
      </div>
      <p className="text-sm text-gray-700 leading-relaxed line-clamp-4">{result.snippet}</p>
    </div>
  )
}

function ImageCard({ result }) {
  const src = thumbnailUrl(result.thumbnailUrl)

  return (
    <div className="card p-3 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-gray-400 text-xs">🖼</span>
        <span className="text-xs font-medium text-purple-700 truncate flex-1">{result.fileName}</span>
        <ScoreBadge score={result.score} />
      </div>
      {src ? (
        <img
          src={src}
          alt={result.fileName}
          className="w-full rounded-lg object-contain max-h-48 bg-gray-100"
          onError={e => { e.target.style.display = 'none' }}
        />
      ) : (
        <div className="w-full h-32 bg-gray-100 rounded-lg flex items-center justify-center text-gray-400 text-3xl">
          🖼
        </div>
      )}
    </div>
  )
}

export default function ResultCard({ result, rank }) {
  return (
    <div className="relative">
      <span className="absolute -left-6 top-3 text-xs text-gray-400 font-mono select-none">
        {rank}
      </span>
      {result.resultType === 'image'
        ? <ImageCard result={result} />
        : <TextChunkCard result={result} />}
    </div>
  )
}
