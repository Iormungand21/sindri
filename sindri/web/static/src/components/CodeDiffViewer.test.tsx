import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CodeDiffViewer } from './CodeDiffViewer'
import type { FileChanges } from '../types/api'

describe('CodeDiffViewer', () => {
  const emptyFileChanges: FileChanges = {
    session_id: 'test-session-123',
    file_changes: [],
    files_modified: [],
    total_changes: 0,
  }

  const mockFileChanges: FileChanges = {
    session_id: 'test-session-456',
    file_changes: [
      {
        file_path: '/tmp/hello.py',
        operation: 'write',
        turn_index: 0,
        timestamp: '2026-01-15T10:00:00',
        success: true,
        new_content: 'print("Hello, World!")',
        content_size: 22,
      },
      {
        file_path: '/tmp/hello.py',
        operation: 'edit',
        turn_index: 1,
        timestamp: '2026-01-15T10:01:00',
        success: true,
        old_text: 'print("Hello, World!")',
        new_text: 'print("Hello, Universe!")',
      },
      {
        file_path: '/tmp/test.py',
        operation: 'read',
        turn_index: 2,
        timestamp: '2026-01-15T10:02:00',
        success: true,
      },
    ],
    files_modified: ['/tmp/hello.py'],
    total_changes: 3,
  }

  it('renders loading state', () => {
    render(<CodeDiffViewer fileChanges={null} isLoading={true} />)
    expect(screen.getByText(/loading file changes/i)).toBeInTheDocument()
  })

  it('renders error state', () => {
    const error = new Error('Failed to fetch')
    render(<CodeDiffViewer fileChanges={null} error={error} />)
    expect(screen.getByText(/failed to load file changes/i)).toBeInTheDocument()
    expect(screen.getByText(/failed to fetch/i)).toBeInTheDocument()
  })

  it('renders empty state when no changes', () => {
    render(<CodeDiffViewer fileChanges={emptyFileChanges} />)
    expect(screen.getByText(/no file changes in this session/i)).toBeInTheDocument()
  })

  it('displays summary with total changes and files modified', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)
    expect(screen.getByText(/total changes:/i)).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText(/files modified:/i)).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('displays operation count badges', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)
    expect(screen.getByText('1 writes')).toBeInTheDocument()
    expect(screen.getByText('1 edits')).toBeInTheDocument()
    expect(screen.getByText('1 reads')).toBeInTheDocument()
  })

  it('renders file change cards', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)
    // Should show file names
    expect(screen.getAllByText('hello.py').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('test.py')).toBeInTheDocument()
  })

  it('shows operation labels on cards', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)
    expect(screen.getByText(/WRITE/)).toBeInTheDocument()
    expect(screen.getByText(/EDIT/)).toBeInTheDocument()
    expect(screen.getByText(/READ/)).toBeInTheDocument()
  })

  it('shows turn index on cards', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)
    expect(screen.getByText(/turn #1/i)).toBeInTheDocument()
    expect(screen.getByText(/turn #2/i)).toBeInTheDocument()
    expect(screen.getByText(/turn #3/i)).toBeInTheDocument()
  })

  it('expands card when clicked', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)

    // Initially collapsed - no content visible
    expect(screen.queryByText('print("Hello, World!")')).not.toBeInTheDocument()

    // Click to expand write card
    const writeCard = screen.getByText(/WRITE/).closest('button')
    if (writeCard) {
      fireEvent.click(writeCard)
    }

    // Now content should be visible
    expect(screen.getByText(/print\("Hello, World!"\)/)).toBeInTheDocument()
  })

  it('shows diff view for edit operations', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)

    // Click to expand edit card
    const editCard = screen.getByText(/EDIT/).closest('button')
    if (editCard) {
      fireEvent.click(editCard)
    }

    // Should show old and new text info
    expect(screen.getByText(/replaced.*line/i)).toBeInTheDocument()
  })

  it('filters by operation type', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)

    // Select writes only
    const operationFilter = screen.getByDisplayValue('All operations')
    fireEvent.change(operationFilter, { target: { value: 'write' } })

    // Should only show write operations
    expect(screen.getByText(/WRITE/)).toBeInTheDocument()
    expect(screen.queryByText(/EDIT/)).not.toBeInTheDocument()
    expect(screen.queryByText(/READ/)).not.toBeInTheDocument()
  })

  it('filters by file', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)

    // Select test.py (test.py is not in files_modified, so we need to use a modified file)
    const fileFilter = screen.getByDisplayValue('All files')
    fireEvent.change(fileFilter, { target: { value: '/tmp/hello.py' } })

    // Should only show hello.py operations (write and edit)
    const operationLabels = screen.getAllByText(/WRITE|EDIT/)
    expect(operationLabels.length).toBe(2)
    // READ for test.py should be filtered out
    expect(screen.queryByText(/READ/)).not.toBeInTheDocument()
  })

  it('expands all cards', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)

    // Click expand all
    const expandAllBtn = screen.getByText(/expand all/i)
    fireEvent.click(expandAllBtn)

    // All cards should be expanded and show content
    // Use getAllByText since the same text appears in both write content and edit diff
    const helloWorldElements = screen.getAllByText(/print\("Hello, World!"\)/)
    expect(helloWorldElements.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/replaced.*line/i)).toBeInTheDocument()
    expect(screen.getByText(/file was read for context/i)).toBeInTheDocument()
  })

  it('collapses all cards', () => {
    render(<CodeDiffViewer fileChanges={mockFileChanges} />)

    // First expand all
    fireEvent.click(screen.getByText(/expand all/i))

    // Then collapse all
    fireEvent.click(screen.getByText(/collapse all/i))

    // Content should not be visible
    expect(screen.queryByText(/print\("Hello, World!"\)/)).not.toBeInTheDocument()
    expect(screen.queryByText(/file was read for context/i)).not.toBeInTheDocument()
  })

  it('shows no matches message when filter excludes all', () => {
    const singleChange: FileChanges = {
      session_id: 'test-session',
      file_changes: [
        {
          file_path: '/tmp/only.py',
          operation: 'write',
          turn_index: 0,
          timestamp: '2026-01-15T10:00:00',
          success: true,
          new_content: 'content',
        },
      ],
      files_modified: ['/tmp/only.py'],
      total_changes: 1,
    }

    render(<CodeDiffViewer fileChanges={singleChange} />)

    // Filter by edit (which doesn't exist)
    const operationFilter = screen.getByDisplayValue('All operations')
    fireEvent.change(operationFilter, { target: { value: 'edit' } })

    expect(screen.getByText(/no changes match the current filter/i)).toBeInTheDocument()
  })

  it('handles null fileChanges gracefully', () => {
    render(<CodeDiffViewer fileChanges={null} />)
    expect(screen.getByText(/no file changes in this session/i)).toBeInTheDocument()
  })
})
