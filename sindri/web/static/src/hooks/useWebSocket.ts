/**
 * WebSocket hook for real-time event streaming
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import type { WebSocketEvent, EventType } from '../types/api'

interface UseWebSocketOptions {
  url?: string
  reconnectInterval?: number
  maxReconnectAttempts?: number
  onMessage?: (event: WebSocketEvent) => void
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Event) => void
}

interface UseWebSocketReturn {
  isConnected: boolean
  lastEvent: WebSocketEvent | null
  events: WebSocketEvent[]
  connect: () => void
  disconnect: () => void
  clearEvents: () => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url = `ws://${window.location.host}/ws`,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    onMessage,
    onConnect,
    onDisconnect,
    onError,
  } = options

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>()

  const [isConnected, setIsConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null)
  const [events, setEvents] = useState<WebSocketEvent[]>([])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    try {
      wsRef.current = new WebSocket(url)

      wsRef.current.onopen = () => {
        setIsConnected(true)
        reconnectAttemptsRef.current = 0
        onConnect?.()
      }

      wsRef.current.onclose = () => {
        setIsConnected(false)
        onDisconnect?.()

        // Attempt reconnection
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++
            connect()
          }, reconnectInterval)
        }
      }

      wsRef.current.onerror = (error) => {
        onError?.(error)
      }

      wsRef.current.onmessage = (messageEvent) => {
        try {
          const event = JSON.parse(messageEvent.data) as WebSocketEvent

          // Skip heartbeat events
          if (event.type === 'heartbeat') {
            return
          }

          setLastEvent(event)
          setEvents((prev) => [...prev.slice(-99), event]) // Keep last 100 events
          onMessage?.(event)
        } catch {
          console.error('Failed to parse WebSocket message:', messageEvent.data)
        }
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
    }
  }, [url, reconnectInterval, maxReconnectAttempts, onMessage, onConnect, onDisconnect, onError])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    reconnectAttemptsRef.current = maxReconnectAttempts // Prevent reconnection
    wsRef.current?.close()
    wsRef.current = null
    setIsConnected(false)
  }, [maxReconnectAttempts])

  const clearEvents = useCallback(() => {
    setEvents([])
    setLastEvent(null)
  }, [])

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return {
    isConnected,
    lastEvent,
    events,
    connect,
    disconnect,
    clearEvents,
  }
}

// Helper hook to filter events by type
export function useEventFilter(
  events: WebSocketEvent[],
  types: EventType[]
): WebSocketEvent[] {
  return events.filter((event) => types.includes(event.type as EventType))
}
