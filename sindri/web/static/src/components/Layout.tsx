/**
 * Layout - Main app layout with navigation
 */

import { Link, useLocation } from 'react-router-dom'
import { useHealth } from '../hooks/useApi'

interface LayoutProps {
  children: React.ReactNode
}

export function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const { data: health } = useHealth()

  const navItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/agents', label: 'Agents', icon: '🤖' },
    { path: '/sessions', label: 'Sessions', icon: '📝' },
  ]

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-sindri-900 border-b border-sindri-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-3">
              <svg
                className="w-8 h-8 text-forge-500"
                viewBox="0 0 64 64"
                fill="none"
              >
                <circle
                  cx="32"
                  cy="32"
                  r="30"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  d="M20 44 L32 20 L44 44"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M24 36 L40 36"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                />
                <circle cx="32" cy="28" r="4" fill="currentColor" />
              </svg>
              <span className="text-xl font-bold text-sindri-100">Sindri</span>
            </Link>

            {/* Navigation */}
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    location.pathname === item.path
                      ? 'bg-sindri-700 text-sindri-100'
                      : 'text-sindri-400 hover:text-sindri-100 hover:bg-sindri-800'
                  }`}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>

            {/* Status */}
            <div className="flex items-center gap-3">
              <span
                className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs ${
                  health?.status === 'healthy'
                    ? 'bg-green-900/50 text-green-400'
                    : 'bg-yellow-900/50 text-yellow-400'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    health?.status === 'healthy' ? 'bg-green-400' : 'bg-yellow-400'
                  }`}
                />
                API {health?.status === 'healthy' ? 'Connected' : 'Checking...'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="bg-sindri-900 border-t border-sindri-700 py-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-sindri-500">
            Sindri - Local LLM Orchestration •{' '}
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-forge-400 hover:text-forge-300"
            >
              API Docs
            </a>
          </p>
        </div>
      </footer>
    </div>
  )
}
