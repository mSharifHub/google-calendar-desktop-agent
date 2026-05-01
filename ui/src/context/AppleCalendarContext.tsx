import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { SERVER_URL } from '../types'

interface AppleCalendarContextType {
  isConnected: boolean
  connecting: boolean
  error: string
  /** Connect using an Apple ID and an app-specific password from appleid.apple.com. */
  connect: (username: string, appPassword: string) => Promise<void>
  disconnect: () => Promise<void>
  refresh: () => Promise<void>
}

const AppleCalendarContext = createContext<AppleCalendarContextType | null>(null)

export function AppleCalendarProvider({ children }: { children: ReactNode }) {
  const [isConnected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError]           = useState('')

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${SERVER_URL}/calendars/status`)
      if (res.ok) {
        const data = await res.json()
        setConnected(!!data.apple)
      }
    } catch { /* backend unreachable */ }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const connect = async (username: string, appPassword: string) => {
    setConnecting(true)
    setError('')
    try {
      const res = await fetch(`${SERVER_URL}/auth/apple/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, app_password: appPassword }),
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
      await fetch(`${SERVER_URL}/auth/apple/disconnect`, { method: 'POST' })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Disconnect failed')
    } finally {
      setConnecting(false)
    }
  }

  return (
    <AppleCalendarContext.Provider value={{ isConnected, connecting, error, connect, disconnect, refresh }}>
      {children}
    </AppleCalendarContext.Provider>
  )
}

export function useAppleCalendar(): AppleCalendarContextType {
  const ctx = useContext(AppleCalendarContext)
  if (!ctx) throw new Error('useAppleCalendar must be used inside AppleCalendarProvider')
  return ctx
}
