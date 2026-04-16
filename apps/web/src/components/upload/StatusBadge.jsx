const CONFIG = {
  PENDING_UPLOAD: { label: 'Pending',    cls: 'bg-gray-100 text-gray-600' },
  UPLOADED:       { label: 'Queued',     cls: 'bg-yellow-100 text-yellow-700' },
  PROCESSING:     { label: 'Processing', cls: 'bg-blue-100 text-blue-700', spin: true },
  READY:          { label: 'Ready',      cls: 'bg-green-100 text-green-700' },
  FAILED:         { label: 'Failed',     cls: 'bg-red-100 text-red-700' },
}

export default function StatusBadge({ status }) {
  const cfg = CONFIG[status] ?? CONFIG.PENDING_UPLOAD
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.cls}`}>
      {cfg.spin && (
        <span className="inline-block w-2.5 h-2.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
      )}
      {cfg.label}
    </span>
  )
}
