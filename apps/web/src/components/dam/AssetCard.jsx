/** Grid-view card for a single asset. */
import StatusBadge from '../upload/StatusBadge'

const TYPE_ICON = { pdf: '📄', docx: '📝', doc: '📝', jpg: '🖼', jpeg: '🖼', png: '🖼', webp: '🖼', gif: '🖼' }
const IMAGE_TYPES = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif'])

function FileSize({ bytes }) {
  if (!bytes) return null
  if (bytes < 1024) return <span>{bytes} B</span>
  if (bytes < 1024 * 1024) return <span>{(bytes / 1024).toFixed(1)} KB</span>
  return <span>{(bytes / (1024 * 1024)).toFixed(1)} MB</span>
}

export default function AssetCard({ asset, onClick, onDelete }) {
  const isImage = IMAGE_TYPES.has(asset.fileType?.toLowerCase())
  const icon = TYPE_ICON[asset.fileType?.toLowerCase()] || '📎'

  return (
    <div
      className="bg-white rounded-xl border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group overflow-hidden flex flex-col"
      onClick={() => onClick(asset)}
    >
      {/* Thumbnail */}
      <div className="relative bg-gray-50 h-44 flex items-center justify-center overflow-hidden">
        {asset.thumbnailUrl ? (
          <img
            src={asset.thumbnailUrl}
            alt={asset.fileName}
            className="w-full h-full object-cover"
            onError={e => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex' }}
          />
        ) : null}
        <div
          className="absolute inset-0 flex items-center justify-center text-5xl"
          style={{ display: asset.thumbnailUrl ? 'none' : 'flex' }}
        >
          {icon}
        </div>

        {/* Type badge */}
        <span className="absolute top-2 left-2 bg-black/50 text-white text-xs px-2 py-0.5 rounded-full uppercase font-mono">
          {asset.fileType}
        </span>

        {/* Delete button */}
        <button
          className="absolute top-2 right-2 bg-red-500 text-white rounded-full w-6 h-6 text-xs hidden group-hover:flex items-center justify-center hover:bg-red-600 transition-colors"
          onClick={e => { e.stopPropagation(); onDelete(asset) }}
          title="Delete"
        >
          ×
        </button>
      </div>

      {/* Info */}
      <div className="p-3 flex flex-col gap-1 flex-1">
        <p className="text-sm font-medium text-gray-900 truncate" title={asset.fileName}>
          {asset.fileName}
        </p>
        <div className="flex items-center justify-between">
          <StatusBadge status={asset.status} />
          <span className="text-xs text-gray-400"><FileSize bytes={asset.sizeBytes} /></span>
        </div>
        {asset.status === 'READY' && (
          <div className="flex gap-3 text-xs text-gray-500 mt-1">
            {asset.chunkCount > 0 && <span>{asset.chunkCount} chunks</span>}
            {asset.imageCount > 0 && <span>{asset.imageCount} images</span>}
            {asset.pageCount > 0 && <span>{asset.pageCount} pages</span>}
          </div>
        )}
        {asset.errorMessage && (
          <p className="text-xs text-red-500 truncate mt-1" title={asset.errorMessage}>
            {asset.errorMessage}
          </p>
        )}
      </div>
    </div>
  )
}
