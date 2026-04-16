/**
 * API client — all backend calls go through here.
 *
 * In dev, Vite proxies /api/* → http://localhost:8000
 * In production, set VITE_API_URL to the EC2 / ALB address.
 */

const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')  // strip trailing slash
  : '/api'                                             // use Vite proxy in dev

async function _json(resp) {
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText)
    throw new Error(`API ${resp.status}: ${text}`)
  }
  return resp.json()
}

/** Upload a File object via multipart POST. Returns { fileId, s3Key }. */
export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const resp = await fetch(`${BASE}/upload/local`, { method: 'POST', body: form })
  return _json(resp)
}

/** Poll file status. Returns { fileId, status, pageCount, errorMessage }. */
export async function getFileStatus(fileId) {
  const resp = await fetch(`${BASE}/files/${fileId}/status`)
  return _json(resp)
}

/**
 * Run a hybrid search query.
 * Returns { queryType, answer, results }.
 */
export async function search({ query, topK = 8, includeAnswer = false, fileTypes = [] }) {
  const resp = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, topK, includeAnswer, filters: { fileTypes } }),
  })
  return _json(resp)
}

/** Resolve a thumbnail URL (may be a local storage path from the API). */
export function thumbnailUrl(rawUrl) {
  if (!rawUrl) return null
  if (rawUrl.startsWith('http')) return rawUrl
  // For local dev: serve from the API's static-file proxy
  return `${BASE}/files/thumbnail/${encodeURIComponent(rawUrl)}`
}

/** List all uploaded files (DAM). Returns FileAssetOut[]. */
export async function listFiles() {
  const resp = await fetch(`${BASE}/files`)
  return _json(resp)
}

/** Get full asset detail with embedding preview. Returns FileDetailOut. */
export async function getFileDetail(fileId) {
  const resp = await fetch(`${BASE}/files/${fileId}/detail`)
  return _json(resp)
}

/** Delete a file and all its indexed data. */
export async function deleteFile(fileId) {
  const resp = await fetch(`${BASE}/files/${fileId}`, { method: 'DELETE' })
  if (resp.status === 204) return
  throw new Error(`Delete failed: ${resp.status}`)
}
