import { useEffect, useRef, KeyboardEvent } from 'react'
import { useChat } from '../context/ChatContext'

export default function ChatPanel() {
  const { activeThread, loading, handleSend, setView, userName, userPicture } = useChat()
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  const messages  = activeThread?.messages ?? []
  const modelInfo = activeThread ? `${activeThread.config.backend} · ${activeThread.config.modelName || 'default'}` : ''
  const initials  = userName ? userName.charAt(0).toUpperCase() : 'U'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const submit = () => {
    const text = inputRef.current?.value.trim()
    if (!text || loading) return
    handleSend(text)
    if (inputRef.current) {
      inputRef.current.value = ''
      inputRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleInput = () => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 160) + 'px'
    }
  }

  const isEmpty = messages.length === 0

  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Top bar */}
      <header className="flex items-center justify-between mx-10 px-8 py-5 border-b border-gray-100">
        <span className="text-2xl font-medium text-gray-800">📅 Calendar Assistant</span>
        <div className="flex items-center gap-4 ml-auto">
          {modelInfo && (
            <span className="text-sm text-gray-400 bg-gray-100 px-4 py-1.5 rounded-full">{modelInfo}</span>
          )}
          <button
            onClick={() => setView('settings')}
            className="text-gray-500 hover:text-gray-800 transition-colors text-base px-4 py-2
                       rounded-full hover:bg-gray-100 font-medium"
          >
            Settings
          </button>
          {/* User avatar */}
          {userPicture ? (
            <img src={userPicture} alt={userName} className="w-9 h-9 rounded-full object-cover" />
          ) : (
            <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center
                            text-white text-sm font-semibold flex-shrink-0">
              {initials}
            </div>
          )}
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full min-h-[60vh] gap-6">
            <span className="text-8xl">📅</span>
            <h2 className="text-4xl font-medium text-gray-700">
              What's on your calendar?
              <span className="cursor-blink inline-block w-0.5 h-[1.1em] bg-blue-500 ml-2 align-middle rounded-sm" />
            </h2>
            <p className="text-gray-400 text-xl">Ask me about your events, schedule, or availability.</p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto px-6 py-10 flex flex-col gap-8">
            {messages.map(m => (
              <div key={m.id} className={`flex items-end gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' && (
                  <div className="w-9 h-9 rounded-full bg-blue-100 flex items-center justify-center
                                  text-lg flex-shrink-0 mb-0.5">
                    📅
                  </div>
                )}

                <div className={`flex flex-col gap-1 max-w-[75%] ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <span className="text-xs text-gray-400 px-1">
                    {m.role === 'user' ? (userName || 'You') : 'Calendar AI'}
                  </span>
                  <div
                    className={`px-6 py-4 rounded-2xl text-lg leading-relaxed whitespace-pre-wrap
                      ${m.role === 'user'
                        ? 'bg-blue-600 text-white rounded-br-sm'
                        : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                      }`}
                  >
                    {m.content}
                  </div>
                </div>

                {m.role === 'user' && (
                  userPicture
                    ? <img src={userPicture} alt={userName} className="w-9 h-9 rounded-full object-cover flex-shrink-0 mb-0.5" />
                    : <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center
                                      text-white text-sm font-semibold flex-shrink-0 mb-0.5">
                        {initials}
                      </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center
                                text-xl flex-shrink-0 mr-4">
                  📅
                </div>
                <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-6 py-4 flex gap-2 items-center">
                  {[0, 150, 300].map(delay => (
                    <span
                      key={delay}
                      className="w-2.5 h-2.5 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${delay}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      {/* Input bar */}
      <div className="border-t border-gray-100 bg-white px-6 py-5">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-end gap-4 bg-gray-100 rounded-3xl px-6 py-4">
            <textarea
              ref={inputRef}
              rows={1}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              placeholder="Ask about your calendar…"
              disabled={loading}
              className="flex-1 bg-transparent text-lg text-gray-800 placeholder-gray-400
                         outline-none resize-none max-h-[160px] overflow-y-auto font-[inherit]
                         disabled:opacity-50"
            />
            <button
              onClick={submit}
              disabled={loading}
              className="w-11 h-11 rounded-full bg-blue-600 hover:bg-blue-700 disabled:opacity-40
                         disabled:cursor-not-allowed text-white flex items-center justify-center
                         transition-colors flex-shrink-0 text-xl"
            >
              ↑
            </button>
          </div>
          <p className="text-center text-sm text-gray-400 mt-2">Press Enter to send · Shift+Enter for new line</p>
        </div>
      </div>
    </div>
  )
}
