import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { SERVER_URL } from '../types'

interface CalendlyContextType {
  isConnected: boolean
  connecting: boolean
  error: string
  /** Connect using a Personal Access Token from Calendly → Integrations → API & Webhooks. */
  connect: (token: string) => Promise<void>
  disconnect: () => Promise<void>
  refresh: () => Promise<void>
}

const CalendlyContext = createContext<CalendlyContextType | null>(null)

export function CalendlyProvider({ children }: { children: ReactNode }) {
  const [isConnected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError]           = useState('')

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${SERVER_URL}/calendars/status`)
      if (res.ok) {
        const data = await res.json()
        setConnected(!!data.calendly)
      }
    } catch { /* backend unreachable */ }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const connect = async (token: string) => {
    setConnecting(true)
    setError('')
    try {
      const res = await fetch(`${SERVER_URL}/auth/calendly/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Connection failed')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed')
    } finally {
      setConnecting(false)
    }
  }

  const disconnect = async () => {
    setConnecting(true)
    setError('')
    try {
      await fetch(`${SERVER_URL}/auth/calendly/disconnect`, { method: 'POST' })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Disconnect failed')
    } finally {
      setConnecting(false)
    }
  }

  return (
    <CalendlyContext.Provider value={{ isConnected, connecting, error, connect, disconnect, refresh }}>
      {children}
    </CalendlyContext.Provider>
  )
}

export function useCalendly(): CalendlyContextType {
  const ctx = useContext(CalendlyContext)
  if (!ctx) throw new Error('useCalendly must be used inside CalendlyProvider')
  return ctx
}
