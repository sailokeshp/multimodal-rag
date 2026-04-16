/** Slide-in panel showing full asset metadata + SigLIP2 embedding preview. */
import { useEffect, useState } from 'react'
import { getFileDetail } from '../../api'
import StatusBadge from '../upload/StatusBadge'

function Section({ title, children }) {
  return (
    <div className="mb-5">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">{title}</h3>
      {children}
    </div>
  )
}

function MetaRow({ label, value }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex justify-between py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-xs text-gray-800 font-medium text-right max-w-[60%] break-all">{value}</span>
    </div>
  )
}

function EmbeddingDisplay({ embedding, label }) {
  if (!embedding) return (
    <div className="text-xs text-gray-400 italic py-2">Not yet embedded</div>
  )
  return (
    <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs">
      <div className="text-gray-400 mb-1.5 text-[10px]">{label} · dim={embedding.dim} · norm≈{embedding.norm}</div>
      <div className="text-green-400 leading-relaxed break-all">
        [{embedding.sample.map((v, i) => (
          <span key={i}>
            <span className="text-blue-300">{v.toFixed(5)}</span>
            {i < embedding.sample.length - 1 ? <span className="text-gray-500">, </span> : null}
          </span>
        ))}
        <span className="text-gray-500">, ...</span>]
      </div>
      <div className="text-gray-500 text-[10px] mt-1.5">{embedding.model}</div>
    </div>
  )
}

function formatBytes(b) {
  if (!b) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export default function AssetDetailPanel({ asset, onClose, onDelete }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeImage, setActiveImage] = useState(0)

  useEffect(() => {
    if (!asset) return
    setLoading(true)
    setDetail(null)
    setActiveImage(0)
    getFileDetail(asset.fileId)
      .then(setDetail)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [asset?.fileId])

  if (!asset) return null

  const img = detail?.images?.[activeImage]

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-md bg-white z-50 shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between p-4 border-b border-gray-200 bg-gray-50">
          <div className="min-w-0 flex-1 pr-3">
            <p className="text-sm font-semibold text-gray-900 truncate">{asset.fileName}</p>
            <div className="flex items-center gap-2 mt-1">
              <StatusBadge status={asset.status} />
              <span className="text-xs text-gray-400 uppercase font-mono">{asset.fileType}</span>
              <span className="text-xs text-gray-400">{formatBytes(asset.sizeBytes)}</span>
            </div>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <button
              onClick={() => onDelete(asset)}
              className="text-xs text-red-500 hover:text-red-700 px-2 py-1 rounded hover:bg-red-50 transition-colors"
            >
              Delete
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-700 text-xl leading-none px-1"
            >
              ×
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
              Loading metadata…
            </div>
          ) : (
            <>
              {/* Image preview */}
              {detail?.images?.length > 0 && (
                <Section title={`Images (${detail.images.length})`}>
                  <div className="bg-gray-100 rounded-xl overflow-hidden mb-2 flex items-center justify-center h-52">
                    {img?.thumbnailUrl ? (
                      <img src={img.thumbnailUrl} alt="" className="max-h-full max-w-full object-contain" />
                    ) : (
                      <span className="text-5xl">🖼</span>
                    )}
                  </div>
                  {/* Image selector */}
                  {detail.images.length > 1 && (
                    <div className="flex gap-1.5 overflow-x-auto pb-1">
                      {detail.images.map((im, i) => (
                        <button
                          key={im.imageId}
                          onClick={() => setActiveImage(i)}
                          className={`w-10 h-10 rounded-lg overflow-hidden flex-shrink-0 border-2 transition-all ${i === activeImage ? 'border-blue-500' : 'border-transparent'}`}
                        >
                          {im.thumbnailUrl
                            ? <img src={im.thumbnailUrl} className="w-full h-full object-cover" alt="" />
                            : <div className="w-full h-full bg-gray-200 flex items-center justify-center text-xs">🖼</div>
                          }
                        </button>
                      ))}
                    </div>
                  )}
                </Section>
              )}

              {/* File properties */}
              <Section title="File Properties">
                <div className="rounded-lg bg-gray-50 px-3 py-1">
                  <MetaRow label="File ID" value={asset.fileId} />
                  <MetaRow label="MIME type" value={asset.mimeType} />
                  <MetaRow label="Size" value={formatBytes(asset.sizeBytes)} />
                  <MetaRow label="Pages" value={asset.pageCount} />
                  <MetaRow label="Uploaded" value={formatDate(asset.uploadedAt)} />
                  <MetaRow label="Processed" value={detail?.processedAt ? formatDate(detail.processedAt) : null} />
                  <MetaRow label="Status" value={asset.status} />
                  {asset.errorMessage && <MetaRow label="Error" value={asset.errorMessage} />}
                </div>
              </Section>

              {/* Index stats */}
              {asset.status === 'READY' && (
                <Section title="Index Stats">
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: 'Text Chunks', value: detail?.chunkCount ?? asset.chunkCount },
                      { label: 'Images', value: detail?.imageCount ?? asset.imageCount },
                      { label: 'Pages', value: asset.pageCount ?? '—' },
                    ].map(s => (
                      <div key={s.label} className="bg-blue-50 rounded-lg p-2.5 text-center">
                        <div className="text-xl font-bold text-blue-700">{s.value}</div>
                        <div className="text-xs text-blue-500 mt-0.5">{s.label}</div>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* SigLIP2 vector embedding */}
              {img && (
                <Section title="SigLIP2 Vector Embedding">
                  <p className="text-xs text-gray-500 mb-2">
                    What gets embedded into the {detail?.imageEmbeddingDim}d vector space for image similarity search:
                    {img.caption && <span className="italic"> "{img.caption}"</span>}
                  </p>
                  <EmbeddingDisplay
                    embedding={img.embedding}
                    label="image_embedding"
                  />
                  {img.ocrText && (
                    <div className="mt-2 bg-yellow-50 border border-yellow-200 rounded-lg p-2.5">
                      <p className="text-xs font-medium text-yellow-700 mb-1">OCR Text</p>
                      <p className="text-xs text-yellow-900 leading-relaxed">{img.ocrText}</p>
                    </div>
                  )}
                  {img.width && (
                    <p className="text-xs text-gray-400 mt-1.5">{img.width} × {img.height}px</p>
                  )}
                </Section>
              )}

              {/* Text embedding model info */}
              {detail?.chunks?.length > 0 && (
                <Section title="Text Embedding Model">
                  <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs">
                    <div className="text-gray-400 text-[10px] mb-1">text_embedding · dim={detail.textEmbeddingDim}</div>
                    <div className="text-purple-400">{detail.textEmbeddingModel}</div>
                  </div>
                  <div className="mt-2 space-y-1.5">
                    {detail.chunks.map(c => (
                      <div key={c.chunkId} className="bg-gray-50 rounded-lg p-2.5 text-xs">
                        <div className="flex gap-2 text-gray-400 mb-1">
                          <span className="uppercase font-mono">{c.chunkType}</span>
                          {c.pageStart && <span>p.{c.pageStart}</span>}
                          {c.sectionTitle && <span className="truncate">§ {c.sectionTitle}</span>}
                        </div>
                        <p className="text-gray-700 leading-relaxed">{c.contentPreview}…</p>
                      </div>
                    ))}
                  </div>
                </Section>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
