import { useState } from 'react'
import { uploadFile } from '../../api'
import DropZone from './DropZone'
import FileRow from './FileRow'

const ready = f => f.status === 'READY'
const failed = f => f.status === 'FAILED'

export default function UploadView({ onSwitchToSearch }) {
  const [files, setFiles] = useState([])   // [{ id, name, size, status, errorMessage }]
  const [uploading, setUploading] = useState(false)

  const addFiles = async selectedFiles => {
    setUploading(true)
    const entries = selectedFiles.map(f => ({
      id: null, name: f.name, size: f.size, status: 'PENDING_UPLOAD', errorMessage: null, _file: f,
    }))
    setFiles(prev => [...entries, ...prev])

    for (const entry of entries) {
      try {
        const { fileId } = await uploadFile(entry._file)
        setFiles(prev => prev.map(f =>
          f.name === entry.name && f.id === null
            ? { ...f, id: fileId, status: 'UPLOADED' }
            : f
        ))
      } catch (err) {
        setFiles(prev => prev.map(f =>
          f.name === entry.name && f.id === null
            ? { ...f, status: 'FAILED', errorMessage: err.message }
            : f
        ))
      }
    }
    setUploading(false)
  }

  const updateStatus = (id, status, errorMessage) => {
    setFiles(prev => prev.map(f => f.id === id ? { ...f, status, errorMessage } : f))
  }

  const readyCount = files.filter(ready).length
  const failedCount = files.filter(failed).length
  const total = files.length

  return (
    <div className="space-y-5">
      {/* Drop zone */}
      <DropZone onFiles={addFiles} disabled={uploading} />

      {/* Stats bar */}
      {total > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex gap-4 text-sm text-gray-500">
            <span><span className="font-semibold text-gray-900">{total}</span> files</span>
            {readyCount > 0 && <span className="text-green-600">✓ {readyCount} ready</span>}
            {failedCount > 0 && <span className="text-red-500">✗ {failedCount} failed</span>}
          </div>
          {readyCount > 0 && (
            <button onClick={onSwitchToSearch} className="btn-primary">
              Search these files →
            </button>
          )}
        </div>
      )}

      {/* File list */}
      {files.length > 0 && (
        <div className="card divide-y divide-gray-100">
          {files.map((f, i) => (
            <FileRow
              key={f.id ?? `pending-${i}`}
              file={f}
              onStatusChange={updateStatus}
            />
          ))}
        </div>
      )}

      {/* Empty state */}
      {files.length === 0 && (
        <div className="text-center py-8 text-gray-400 text-sm">
          No files uploaded yet. Drop some above to get started.
        </div>
      )}
    </div>
  )
}
