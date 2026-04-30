import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faBars } from '@fortawesome/free-solid-svg-icons'
import { useChat } from '../context/ChatContext'
import { Thread } from '../types'

interface Props {
  onToggle: () => void
}

function groupByDate(threads: Thread[]): { label: string; items: Thread[] }[] {
  const now = Date.now()
  const groups: Record<string, Thread[]> = {}

  for (const t of threads) {
    const days = Math.floor((now - t.createdAt) / 86_400_000)
    const label =
      days === 0 ? 'Today' :
      days === 1 ? 'Yesterday' :
      days < 7   ? 'Previous 7 days' :
      days < 30  ? 'Previous 30 days' :
      new Date(t.createdAt).toLocaleDateString('en', { month: 'long', year: 'numeric' })

    if (!groups[label]) groups[label] = []
    groups[label].push(t)
  }

  const order = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days']
  const sorted = Object.keys(groups).sort((a, b) => {
    const ai = order.indexOf(a)
    const bi = order.indexOf(b)
    if (ai !== -1 && bi !== -1) return ai - bi
    if (ai !== -1) return -1
    if (bi !== -1) return 1
    return b.localeCompare(a)
  })

  return sorted.map(label => ({ label, items: groups[label] }))
}

export default function Sidebar({ onToggle }: Props) {
  const { threads, activeThreadId, switchThread, deleteThread, startNewChat } = useChat()
  const groups = groupByDate(threads)

  return (
    <aside className="w-64 h-screen flex flex-col bg-white">
      {/* Top: logo + collapse */}
      <div className="flex items-center justify-between px-3 pt-4 pb-2">
        <div className="flex items-center gap-2 px-2">

        </div>
        <button
          onClick={onToggle}
          title="Close sidebar"
          className="p-2 rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100
                     transition-all cursor-pointer"
        >
          <FontAwesomeIcon icon={faBars} className="w-10 h-10" />
        </button>
      </div>

      {/* New chat button */}
      <div className="px-3 py-2">
        <button
          onClick={startNewChat}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-full bg-blue-50
                     hover:bg-blue-100 transition-colors text-blue-700 font-medium text-sm cursor-pointer"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New chat
        </button>
      </div>

      {/* Thread list grouped by date */}
      <nav className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-4">
        {threads.length === 0 && (
          <p className="text-xs text-gray-400 text-center mt-10">No chats yet</p>
        )}

        {groups.map(({ label, items }) => (
          <div key={label}>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 px-3 mb-1">
              {label}
            </p>
            <div className="flex flex-col gap-0.5">
              {items.map(thread => {
                const isActive = thread.id === activeThreadId
                return (
                  <div
                    key={thread.id}
                    onClick={() => switchThread(thread.id)}
                    className={`group flex items-center justify-between px-3 py-2.5 rounded-xl
                                cursor-pointer transition-colors select-none
                                ${isActive
                                  ? 'bg-blue-50 text-blue-700'
                                  : 'text-gray-600 hover:bg-gray-100'}`}
                  >
                    <p className="text-sm truncate flex-1">{thread.title}</p>
                    <button
                      onClick={e => { e.stopPropagation(); deleteThread(thread.id) }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity ml-1 flex-shrink-0
                                 text-gray-400 hover:text-red-400 cursor-pointer text-lg leading-none"
                      title="Delete"
                    >
                      ×
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  )
}
