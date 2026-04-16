/** List-view row for a single asset. */
import StatusBadge from '../upload/StatusBadge'

const TYPE_ICON = { pdf: '📄', docx: '📝', doc: '📝', jpg: '🖼', jpeg: '🖼', png: '🖼', webp: '🖼' }

function FileSize({ bytes }) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function AssetRow({ asset, onClick, onDelete }) {
  const icon = TYPE_ICON[asset.fileType?.toLowerCase()] || '📎'

  return (
    <tr
      className="hover:bg-blue-50 cursor-pointer transition-colors group"
      onClick={() => onClick(asset)}
    >
      {/* Thumbnail + name */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg overflow-hidden bg-gray-100 flex-shrink-0 flex items-center justify-center text-xl">
            {asset.thumbnailUrl ? (
              <img
                src={asset.thumbnailUrl}
                alt={asset.fileName}
                className="w-full h-full object-cover"
                onError={e => { e.target.style.display = 'none' }}
              />
            ) : icon}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate max-w-xs">{asset.fileName}</p>
            <p className="text-xs text-gray-400 uppercase font-mono">{asset.fileType}</p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3"><StatusBadge status={asset.status} /></td>
      <td className="px-4 py-3 text-sm text-gray-600">{FileSize({ bytes: asset.sizeBytes })}</td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {asset.pageCount ? `${asset.pageCount}p` : '—'}
        {asset.chunkCount > 0 && <span className="text-xs text-gray-400 ml-1">· {asset.chunkCount} chunks</span>}
      </td>
      <td className="px-4 py-3 text-xs text-gray-500">{formatDate(asset.uploadedAt)}</td>
      <td className="px-4 py-3 text-right">
        <button
          className="text-xs text-red-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-all px-2 py-1 rounded hover:bg-red-50"
          onClick={e => { e.stopPropagation(); onDelete(asset) }}
        >
          Delete
        </button>
      </td>
    </tr>
  )
}
