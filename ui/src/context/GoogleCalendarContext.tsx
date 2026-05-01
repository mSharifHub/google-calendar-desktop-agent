import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { SERVER_URL } from '../types'

interface GoogleCalendarState {
  isConnected: boolean
  connecting: boolean    // OAuth flow in progress (blocking browser)
  error: string
}

interface GoogleCalendarContextType extends GoogleCalendarState {
  connect: () => Promise<void>
  disconnect: () => Promise<void>
  refresh: () => Promise<void>
}

const GoogleCalendarContext = createContext<GoogleCalendarContextType | null>(null)

export function GoogleCalendarProvider({ children }: { children: ReactNode }) {
  const [isConnected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError]           = useState('')

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${SERVER_URL}/calendars/status`)
      if (res.ok) {
        const data = await res.json()
        setConnected(!!data.google)
      }
    } catch { /* backend unreachable */ }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const connect = async () => {
    setConnecting(true)
    setError('')
    try {
      // POST blocks on the backend until the user completes the browser OAuth flow
      const res = await fetch(`${SERVER_URL}/auth/google/connect`, { method: 'POST' })
      if (!res.ok) {
        const d = await res.json()
        throw new Error(d.detail || 'Connection failed')
      }
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
      await fetch(`${SERVER_URL}/auth/google/disconnect`, { method: 'POST' })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Disconnect failed')
    } finally {
      setConnecting(false)
    }
  }

  return (
    <GoogleCalendarContext.Provider value={{ isConnected, connecting, error, connect, disconnect, refresh }}>
      {children}
    </GoogleCalendarContext.Provider>
  )
}

export function useGoogleCalendar(): GoogleCalendarContextType {
  const ctx = useContext(GoogleCalendarContext)
  if (!ctx) throw new Error('useGoogleCalendar must be used inside GoogleCalendarProvider')
  return ctx
}
