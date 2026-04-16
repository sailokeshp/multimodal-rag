/** Main DAM home screen — grid/list view of all assets with polling. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteFile, listFiles } from '../../api'
import AssetCard from './AssetCard'
import AssetRow from './AssetRow'
import AssetDetailPanel from './AssetDetailPanel'

const POLL_INTERVAL = 4000 // re-fetch while any file is PENDING/PROCESSING

function EmptyState({ onUpload }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="text-6xl mb-4">📂</div>
      <h2 className="text-lg font-semibold text-gray-700 mb-2">No assets yet</h2>
      <p className="text-sm text-gray-500 mb-6">Upload documents or images to start building your asset library</p>
      <button
        onClick={onUpload}
        className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
      >
        Upload Files
      </button>
    </div>
  )
}

function ViewToggle({ view, onChange }) {
  return (
    <div className="flex bg-gray-100 rounded-lg p-0.5">
      {[['grid', '⊞'], ['list', '≡']].map(([v, icon]) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={`px-3 py-1.5 rounded-md text-sm transition-all ${
            view === v ? 'bg-white shadow-sm text-blue-700 font-medium' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {icon}
        </button>
      ))}
    </div>
  )
}

export default function AssetBrowser({ onUpload }) {
  const [assets, setAssets] = useState([])
  const [view, setView] = useState('grid')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const timerRef = useRef(null)

  const fetchAssets = useCallback(async () => {
    try {
      const data = await listFiles()
      setAssets(data)
    } catch (e) {
      console.error('Failed to list assets', e)
    } finally {
      setLoading(false)
    }
  }, [])

  // Poll while any asset is still processing
  useEffect(() => {
    fetchAssets()
  }, [fetchAssets])

  useEffect(() => {
    const hasPending = assets.some(a => a.status === 'PENDING' || a.status === 'PROCESSING' || a.status === 'UPLOADED')
    clearInterval(timerRef.current)
    if (hasPending) {
      timerRef.current = setInterval(fetchAssets, POLL_INTERVAL)
    }
    return () => clearInterval(timerRef.current)
  }, [assets, fetchAssets])

  const handleDelete = useCallback(async (asset) => {
    if (!confirm(`Delete "${asset.fileName}"? This removes it from the search index.`)) return
    try {
      await deleteFile(asset.fileId)
      setAssets(prev => prev.filter(a => a.fileId !== asset.fileId))
      if (selected?.fileId === asset.fileId) setSelected(null)
    } catch (e) {
      alert('Delete failed: ' + e.message)
    }
  }, [selected])

  // Filtered assets
  const FILE_TYPES = ['all', 'image', 'document']
  const isImage = ft => ['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ft?.toLowerCase())
  const filtered = assets.filter(a => {
    if (filter === 'image') return isImage(a.fileType)
    if (filter === 'document') return !isImage(a.fileType)
    return true
  })

  const counts = {
    all: assets.length,
    image: assets.filter(a => isImage(a.fileType)).length,
    document: assets.filter(a => !isImage(a.fileType)).length,
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-gray-400 text-sm gap-2">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        Loading assets…
      </div>
    )
  }

  return (
    <div className="relative">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5 gap-3 flex-wrap">
        {/* Filter tabs */}
        <div className="flex gap-1 bg-gray-100 p-0.5 rounded-lg">
          {FILE_TYPES.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-md text-sm capitalize transition-all ${
                filter === f ? 'bg-white shadow-sm text-blue-700 font-medium' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {f} <span className="text-xs opacity-60">({counts[f]})</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">{filtered.length} asset{filtered.length !== 1 ? 's' : ''}</span>
          <ViewToggle view={view} onChange={setView} />
          <button
            onClick={onUpload}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            + Upload
          </button>
        </div>
      </div>

      {/* Empty state */}
      {filtered.length === 0 && (
        assets.length === 0
          ? <EmptyState onUpload={onUpload} />
          : <div className="text-center py-16 text-gray-400 text-sm">No {filter} assets yet</div>
      )}

      {/* Grid view */}
      {view === 'grid' && filtered.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {filtered.map(asset => (
            <AssetCard
              key={asset.fileId}
              asset={asset}
              onClick={setSelected}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* List view */}
      {view === 'list' && filtered.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['Name', 'Status', 'Size', 'Index', 'Uploaded', ''].map(h => (
                  <th key={h} className="px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(asset => (
                <AssetRow
                  key={asset.fileId}
                  asset={asset}
                  onClick={setSelected}
                  onDelete={handleDelete}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail panel */}
      {selected && (
        <AssetDetailPanel
          asset={selected}
          onClose={() => setSelected(null)}
          onDelete={async (asset) => { await handleDelete(asset); setSelected(null) }}
        />
      )}
    </div>
  )
}
