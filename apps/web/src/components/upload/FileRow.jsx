import { useEffect, useRef } from 'react'
import { getFileStatus } from '../../api'
import StatusBadge from './StatusBadge'

const TERMINAL = new Set(['READY', 'FAILED'])
const POLL_MS = 2000

export default function FileRow({ file, onStatusChange }) {
  const timerRef = useRef(null)

  useEffect(() => {
    if (!file.id || TERMINAL.has(file.status)) return

    const poll = async () => {
      try {
        const data = await getFileStatus(file.id)
        onStatusChange(file.id, data.status, data.errorMessage)
        if (TERMINAL.has(data.status)) {
          clearInterval(timerRef.current)
        }
      } catch {
        // network hiccup — keep polling
      }
    }

    timerRef.current = setInterval(poll, POLL_MS)
    poll() // immediate first check
    return () => clearInterval(timerRef.current)
  }, [file.id, file.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const ext = file.name.split('.').pop().toUpperCase()
  const extColor = { PDF: 'bg-red-100 text-red-700', DOCX: 'bg-blue-100 text-blue-700',
    DOC: 'bg-blue-100 text-blue-700', PNG: 'bg-purple-100 text-purple-700',
    JPG: 'bg-purple-100 text-purple-700', JPEG: 'bg-purple-100 text-purple-700',
    WEBP: 'bg-purple-100 text-purple-700' }[ext] ?? 'bg-gray-100 text-gray-600'

  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 rounded-lg transition-colors">
      <span className={`px-2 py-0.5 rounded text-xs font-bold tracking-wide ${extColor}`}>{ext}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
        {file.size && (
          <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(0)} KB</p>
        )}
        {file.errorMessage && (
          <p className="text-xs text-red-500 mt-0.5 truncate">{file.errorMessage}</p>
        )}
      </div>
      <StatusBadge status={file.status} />
    </div>
  )
}
