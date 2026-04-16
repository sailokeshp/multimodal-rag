import { useRef, useState } from 'react'

const ACCEPT = '.pdf,.docx,.doc,.jpg,.jpeg,.png,.webp'
const ACCEPT_MIME = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
  'image/jpeg', 'image/png', 'image/webp',
])

export default function DropZone({ onFiles, disabled }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  const handle = files => {
    const valid = Array.from(files).filter(f => ACCEPT_MIME.has(f.type))
    if (valid.length) onFiles(valid)
    if (valid.length < files.length) {
      alert(`${files.length - valid.length} file(s) skipped — unsupported type.\nAccepted: PDF, DOCX, JPG, PNG, WEBP`)
    }
  }

  const onDrop = e => {
    e.preventDefault()
    setDragging(false)
    if (!disabled) handle(e.dataTransfer.files)
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      className={`relative flex flex-col items-center justify-center gap-3 p-12 rounded-2xl border-2 border-dashed cursor-pointer transition-all select-none
        ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-gray-50'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <div className="text-5xl">📄</div>
      <div className="text-center">
        <p className="text-base font-semibold text-gray-700">
          Drop files here or <span className="text-blue-600 underline">browse</span>
        </p>
        <p className="text-sm text-gray-400 mt-1">PDF, DOCX, JPG, PNG, WEBP · Max 50 MB each</p>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={e => { handle(e.target.files); e.target.value = '' }}
      />
    </div>
  )
}
