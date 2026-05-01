import { useState } from 'react'
import { Backend, SERVER_URL } from '../types'
import { useChat } from '../context/ChatContext'

const BACKENDS: { value: Backend; label: string; description: string }[] = [
  { value: 'local',  label: 'Local (Ollama)',     description: 'Run models locally' },
  { value: 'claude', label: 'Claude (Anthropic)', description: 'claude-sonnet-4-6 by default' },
  { value: 'openai', label: 'OpenAI',             description: 'gpt-4o by default' },
  { value: 'gemini', label: 'Gemini (Google)',    description: 'gemini-2.0-flash by default' },
]

export default function SettingsPanel() {
  const { handleConnect: onConnect, setView } = useChat()
  const [backend, setBackend]         = useState<Backend>('claude')
  const [apiKey, setApiKey]           = useState('')
  const [modelName, setModelName]     = useState('')
  const [error, setError]             = useState('')
  const [connecting, setConnecting]   = useState(false)
  const [pullModel, setPullModel]     = useState<string | null>(null)  // model pending download
  const [pulling, setPulling]         = useState(false)

  const needsKey   = backend !== 'local'
  const isLocal    = backend === 'local'

  const doConfigure = async () => {
    const res = await fetch(`${SERVER_URL}/configure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backend, api_key: apiKey, model_name: modelName }),
    })
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || 'Configuration failed')
    }
    return res.json()
  }

  const handleConnect = async () => {
    if (needsKey && !apiKey.trim()) {
      setError('API key is required for this backend.')
      return
    }
    if (isLocal && !modelName.trim()) {
      setError('Model name is required for the local backend.')
      return
    }
    setError('')
    setConnecting(true)

    try {
      const data = await doConfigure()
      onConnect({ backend, apiKey, modelName, sessionId: data.session_id })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Connection failed'
      if (msg.startsWith('MODEL_NOT_FOUND:')) {
        const name = msg.slice('MODEL_NOT_FOUND:'.length)  // preserve full tag e.g. llama3.1:latest
        setPullModel(name)   // show download prompt
      } else {
        setError(msg)
      }
    } finally {
      setConnecting(false)
    }
  }

  const handlePull = async () => {
    if (!pullModel) return
    setPulling(true)
    setError('')
    try {
      const res = await fetch(`${SERVER_URL}/ollama/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: pullModel }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Download failed')
      }
      setPullModel(null)
      // Automatically retry configure after successful pull
      setConnecting(true)
      const data = await doConfigure()
      onConnect({ backend, apiKey, modelName, sessionId: data.session_id })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
      setPullModel(null)
    } finally {
      setPulling(false)
      setConnecting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-start bg-white px-6 py-40 ">
      <div className=" flex flex-col justify-center items-center w-full max-w-xl  h-225 mb-20 ">
        {/* Title */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-medium text-gray-800 mb-3">
            Calendar Assistant
          </h1>
          <p className="text-gray-500 text-xl">Connect to your AI model to get started</p>
          <button
            onClick={() => setView('providers')}
            className="mt-4 text-sm text-blue-600 hover:text-blue-800 underline underline-offset-2 cursor-pointer"
          >
            ← Manage Calendar Providers
          </button>
        </div>

        <div className="flex flex-col gap-7 w-full">
          {/* Backend selection */}
          <div>
            <label className="block text-base font-medium text-gray-700 mb-3">Choose a Large Language Model</label>
            <div className="grid grid-cols-2 gap-4">
              {BACKENDS.map(b => (
                <button
                  key={b.value}
                  onClick={() => setBackend(b.value)}
                  className={`cursor-pointer flex flex-col items-start px-6 py-6 rounded-2xl border-2 transition-all text-left
                    ${backend === b.value
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300 bg-white'
                    }`}
                >
                  <span className={`text-lg font-medium ${backend === b.value ? 'text-blue-700' : 'text-gray-800'}`}>
                    {b.label}
                  </span>
                  <span className="text-sm text-gray-400 mt-2">{b.description}</span>
                </button>
              ))}
            </div>
          </div>

          {/* API Key */}
          {needsKey && (
            <div>
              <label className="block text-base font-medium text-gray-700 mb-2">API Key</label>
              <input
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="Paste your API key"
                autoComplete="off"
                className="w-full border border-gray-300 rounded-2xl px-5 py-4 text-base text-gray-800
                           outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all
                           placeholder-gray-400"
              />
            </div>
          )}

          {/* Model name — required for local, hidden for others */}
          <div
            className={`overflow-hidden transition-all duration-500 ease-out
              ${isLocal ? 'max-h-40 opacity-100' : 'max-h-0 opacity-0 pointer-events-none'}`}
          >
            <div className={`transition-transform duration-500 ease-out
              ${isLocal ? 'translate-y-0' : '-translate-y-2'}`}
            >
              <label className="block text-base font-medium text-gray-700 mb-2">
                Model Name <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={modelName}
                onChange={e => setModelName(e.target.value)}
                placeholder="e.g. llama3.1:latest"
                tabIndex={isLocal ? 0 : -1}
                className="w-full border border-gray-300 rounded-2xl px-5 py-4 text-base text-gray-800
                           outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all
                           placeholder-gray-400"
              />
            </div>
          </div>

          {/* Error */}
          {error && <p className="text-red-500 text-base">{error}</p>}

          {/* Download confirmation prompt */}
          {pullModel && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 flex flex-col gap-3">
              <p className="text-base text-amber-800 font-medium">Model not found locally</p>
              <p className="text-sm text-amber-700">
                <span className="font-mono bg-amber-100 px-1.5 py-0.5 rounded">{pullModel}</span> is not installed.
                Download it now using Ollama?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={handlePull}
                  disabled={pulling}
                  className="flex-1 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white
                             font-medium text-sm rounded-full py-2.5 transition-colors cursor-pointer"
                >
                  {pulling ? 'Downloading…' : 'Download'}
                </button>
                <button
                  onClick={() => setPullModel(null)}
                  disabled={pulling}
                  className="flex-1 border border-gray-300 hover:bg-gray-50 text-gray-600
                             font-medium text-sm rounded-full py-2.5 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Connect button */}
          {!pullModel && (
            <button
              onClick={handleConnect}
              disabled={connecting}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                         text-white font-medium text-lg rounded-full py-4 transition-colors"
            >
              {connecting ? 'Connecting…' : 'Connect'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
