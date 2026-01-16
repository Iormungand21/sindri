/**
 * Sindri Web UI - Main Application
 */

import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './components/Dashboard'
import { AgentList } from './components/AgentList'
import { SessionList } from './components/SessionList'
import { SessionDetail } from './components/SessionDetail'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<AgentList />} />
        <Route path="/sessions" element={<SessionList />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Layout>
  )
}

function NotFound() {
  return (
    <div className="text-center py-16">
      <h1 className="text-4xl font-bold text-sindri-100 mb-4">404</h1>
      <p className="text-sindri-400">Page not found</p>
      <a
        href="/"
        className="text-forge-400 hover:text-forge-300 mt-4 inline-block"
      >
        Go to Dashboard
      </a>
    </div>
  )
}

export default App
