import { useState } from 'react'
import UploadView from './components/upload/UploadView'
import SearchView from './components/search/SearchView'
import AssetBrowser from './components/dam/AssetBrowser'

const TABS = [
  { id: 'assets', label: '🗂 Assets' },
  { id: 'upload', label: '⬆ Upload' },
  { id: 'search', label: '🔍 Search' },
]

export default function App() {
  const [tab, setTab] = useState('assets')

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl">⚡</span>
            <div>
              <h1 className="text-lg font-bold text-gray-900 leading-tight">Multimodal RAG</h1>
              <p className="text-xs text-gray-500">Semantic search over your documents &amp; images</p>
            </div>
          </div>

          {/* Tab switcher */}
          <nav className="flex gap-1 bg-gray-100 p-1 rounded-lg">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                  tab === t.id
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-5xl mx-auto px-4 py-6">
        {tab === 'assets' && <AssetBrowser onUpload={() => setTab('upload')} />}
        {tab === 'upload' && <UploadView onSwitchToSearch={() => setTab('search')} />}
        {tab === 'search' && <SearchView />}
      </main>
    </div>
  )
}
