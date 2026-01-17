/**
 * CodeDiffViewer - Visualize file changes from a session
 *
 * Shows before/after diffs for edit operations and new content for writes.
 * Uses the diff library for computing text differences.
 */

import { useState, useMemo } from 'react'
import * as Diff from 'diff'
import type { FileChange, FileChanges } from '../types/api'

interface DiffLineProps {
  type: 'added' | 'removed' | 'unchanged'
  content: string
  lineNumber?: number
}

function DiffLine({ type, content, lineNumber }: DiffLineProps) {
  const bgColor = {
    added: 'bg-green-900/30',
    removed: 'bg-red-900/30',
    unchanged: 'bg-transparent',
  }[type]

  const textColor = {
    added: 'text-green-400',
    removed: 'text-red-400',
    unchanged: 'text-gray-300',
  }[type]

  const prefix = {
    added: '+',
    removed: '-',
    unchanged: ' ',
  }[type]

  return (
    <div className={`flex ${bgColor} font-mono text-sm`}>
      {lineNumber !== undefined && (
        <span className="w-12 px-2 text-right text-gray-500 select-none border-r border-gray-700">
          {lineNumber}
        </span>
      )}
      <span className={`px-2 ${textColor} select-none w-4`}>{prefix}</span>
      <pre className={`flex-1 px-2 ${textColor} whitespace-pre-wrap break-all`}>
        {content || ' '}
      </pre>
    </div>
  )
}

interface DiffViewProps {
  oldText: string
  newText: string
  showLineNumbers?: boolean
}

function DiffView({ oldText, newText, showLineNumbers = true }: DiffViewProps) {
  const diffLines = useMemo(() => {
    const changes = Diff.diffLines(oldText, newText)
    const lines: { type: 'added' | 'removed' | 'unchanged'; content: string }[] = []

    for (const change of changes) {
      const changeLines = change.value.split('\n')
      // Remove last empty line from split
      if (changeLines[changeLines.length - 1] === '') {
        changeLines.pop()
      }

      for (const line of changeLines) {
        if (change.added) {
          lines.push({ type: 'added', content: line })
        } else if (change.removed) {
          lines.push({ type: 'removed', content: line })
        } else {
          lines.push({ type: 'unchanged', content: line })
        }
      }
    }

    return lines
  }, [oldText, newText])

  let lineNumber = 0

  return (
    <div className="border border-gray-700 rounded overflow-hidden">
      {diffLines.map((line, idx) => {
        // Only increment line number for non-removed lines
        if (line.type !== 'removed') {
          lineNumber++
        }
        return (
          <DiffLine
            key={idx}
            type={line.type}
            content={line.content}
            lineNumber={showLineNumbers && line.type !== 'removed' ? lineNumber : undefined}
          />
        )
      })}
    </div>
  )
}

interface NewContentViewProps {
  content: string
  showLineNumbers?: boolean
}

function NewContentView({ content, showLineNumbers = true }: NewContentViewProps) {
  const lines = content.split('\n')

  return (
    <div className="border border-gray-700 rounded overflow-hidden">
      {lines.map((line, idx) => (
        <DiffLine
          key={idx}
          type="added"
          content={line}
          lineNumber={showLineNumbers ? idx + 1 : undefined}
        />
      ))}
    </div>
  )
}

interface FileChangeCardProps {
  change: FileChange
  isExpanded: boolean
  onToggle: () => void
}

function FileChangeCard({ change, isExpanded, onToggle }: FileChangeCardProps) {
  const operationColors = {
    read: 'bg-blue-600',
    write: 'bg-green-600',
    edit: 'bg-yellow-600',
  }

  const operationLabels = {
    read: 'READ',
    write: 'WRITE',
    edit: 'EDIT',
  }

  const operationIcons = {
    read: '📖',
    write: '📝',
    edit: '✏️',
  }

  const fileName = change.file_path.split('/').pop() || change.file_path
  const dirPath = change.file_path.split('/').slice(0, -1).join('/')

  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden bg-gray-800/50">
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3 hover:bg-gray-700/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span
            className={`${operationColors[change.operation]} px-2 py-0.5 rounded text-xs font-medium`}
          >
            {operationIcons[change.operation]} {operationLabels[change.operation]}
          </span>
          <div className="text-left">
            <span className="text-white font-medium">{fileName}</span>
            {dirPath && (
              <span className="text-gray-500 text-sm ml-2">{dirPath}/</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-gray-500 text-xs">
            Turn #{change.turn_index + 1}
          </span>
          <span className="text-gray-400">
            {isExpanded ? '▼' : '▶'}
          </span>
        </div>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="border-t border-gray-700 p-4">
          {change.operation === 'edit' && change.old_text && change.new_text ? (
            <div className="space-y-2">
              <div className="text-sm text-gray-400 mb-2">
                Replaced {change.old_text.split('\n').length} line(s) with{' '}
                {change.new_text.split('\n').length} line(s)
              </div>
              <DiffView oldText={change.old_text} newText={change.new_text} />
            </div>
          ) : change.operation === 'write' && change.new_content ? (
            <div className="space-y-2">
              <div className="text-sm text-gray-400 mb-2">
                Created file with {change.new_content.split('\n').length} line(s)
                {change.content_size && ` (${change.content_size} bytes)`}
              </div>
              <NewContentView content={change.new_content} />
            </div>
          ) : change.operation === 'read' ? (
            <div className="text-sm text-gray-400">
              File was read for context
              {change.read_content && (
                <div className="mt-2">
                  <NewContentView content={change.read_content} />
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-gray-500 italic">
              Content not available
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface CodeDiffViewerProps {
  fileChanges: FileChanges | null
  isLoading?: boolean
  error?: Error | null
}

export function CodeDiffViewer({ fileChanges, isLoading, error }: CodeDiffViewerProps) {
  const [expandedChanges, setExpandedChanges] = useState<Set<number>>(new Set())
  const [filterOperation, setFilterOperation] = useState<string | null>(null)
  const [filterFile, setFilterFile] = useState<string | null>(null)

  const toggleChange = (index: number) => {
    setExpandedChanges((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const expandAll = () => {
    if (fileChanges) {
      setExpandedChanges(new Set(fileChanges.file_changes.map((_, i) => i)))
    }
  }

  const collapseAll = () => {
    setExpandedChanges(new Set())
  }

  const filteredChanges = useMemo(() => {
    if (!fileChanges) return []

    return fileChanges.file_changes.filter((change) => {
      if (filterOperation && change.operation !== filterOperation) return false
      if (filterFile && change.file_path !== filterFile) return false
      return true
    })
  }, [fileChanges, filterOperation, filterFile])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8 text-gray-400">
        <span className="animate-spin mr-2">⏳</span>
        Loading file changes...
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 bg-red-900/20 border border-red-700 rounded text-red-400">
        Failed to load file changes: {error.message}
      </div>
    )
  }

  if (!fileChanges || fileChanges.total_changes === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        <div className="text-4xl mb-2">📁</div>
        <div>No file changes in this session</div>
      </div>
    )
  }

  const operationCounts = fileChanges.file_changes.reduce(
    (acc, change) => {
      acc[change.operation] = (acc[change.operation] || 0) + 1
      return acc
    },
    {} as Record<string, number>
  )

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex flex-wrap items-center gap-4 p-3 bg-gray-800/50 rounded-lg border border-gray-700">
        <div className="text-sm">
          <span className="text-gray-400">Total changes: </span>
          <span className="text-white font-medium">{fileChanges.total_changes}</span>
        </div>
        <div className="text-sm">
          <span className="text-gray-400">Files modified: </span>
          <span className="text-white font-medium">
            {fileChanges.files_modified.length}
          </span>
        </div>
        <div className="flex gap-2">
          {operationCounts.write && (
            <span className="bg-green-600 px-2 py-0.5 rounded text-xs">
              {operationCounts.write} writes
            </span>
          )}
          {operationCounts.edit && (
            <span className="bg-yellow-600 px-2 py-0.5 rounded text-xs">
              {operationCounts.edit} edits
            </span>
          )}
          {operationCounts.read && (
            <span className="bg-blue-600 px-2 py-0.5 rounded text-xs">
              {operationCounts.read} reads
            </span>
          )}
        </div>
      </div>

      {/* Filters and Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Operation filter */}
        <select
          value={filterOperation || ''}
          onChange={(e) => setFilterOperation(e.target.value || null)}
          className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm text-white"
        >
          <option value="">All operations</option>
          <option value="write">Writes only</option>
          <option value="edit">Edits only</option>
          <option value="read">Reads only</option>
        </select>

        {/* File filter */}
        <select
          value={filterFile || ''}
          onChange={(e) => setFilterFile(e.target.value || null)}
          className="bg-gray-700 border border-gray-600 rounded px-3 py-1 text-sm text-white max-w-xs"
        >
          <option value="">All files</option>
          {fileChanges.files_modified.map((file) => (
            <option key={file} value={file}>
              {file.split('/').pop()}
            </option>
          ))}
        </select>

        <div className="flex-1" />

        {/* Expand/Collapse buttons */}
        <button
          onClick={expandAll}
          className="text-sm text-blue-400 hover:text-blue-300"
        >
          Expand all
        </button>
        <span className="text-gray-600">|</span>
        <button
          onClick={collapseAll}
          className="text-sm text-blue-400 hover:text-blue-300"
        >
          Collapse all
        </button>
      </div>

      {/* File changes list */}
      <div className="space-y-3">
        {filteredChanges.map((change) => {
          const originalIndex = fileChanges.file_changes.indexOf(change)
          return (
            <FileChangeCard
              key={originalIndex}
              change={change}
              isExpanded={expandedChanges.has(originalIndex)}
              onToggle={() => toggleChange(originalIndex)}
            />
          )
        })}
      </div>

      {filteredChanges.length === 0 && (
        <div className="p-4 text-center text-gray-500">
          No changes match the current filter
        </div>
      )}
    </div>
  )
}

export default CodeDiffViewer
