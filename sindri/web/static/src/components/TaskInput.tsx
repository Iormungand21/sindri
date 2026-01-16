/**
 * TaskInput - Form for submitting new tasks
 */

import { useState, FormEvent } from 'react'

interface TaskInputProps {
  onSubmit: (description: string) => Promise<void>
  isLoading?: boolean
}

export function TaskInput({ onSubmit, isLoading }: TaskInputProps) {
  const [description, setDescription] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!description.trim() || isLoading) return

    try {
      await onSubmit(description.trim())
      setDescription('')
    } catch {
      // Error handled by parent
    }
  }

  const examples = [
    'Create a Python function to validate email addresses',
    'Write unit tests for the user authentication module',
    'Review the code in src/api/ for security issues',
    'Refactor the database models to use async/await',
  ]

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe your task..."
          className="input flex-1"
          disabled={isLoading}
        />
        <button
          type="submit"
          disabled={!description.trim() || isLoading}
          className="btn btn-primary whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <LoadingSpinner />
              Running...
            </span>
          ) : (
            'Run Task'
          )}
        </button>
      </form>

      <div>
        <p className="text-xs text-sindri-500 mb-2">Try an example:</p>
        <div className="flex flex-wrap gap-2">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setDescription(example)}
              className="text-xs px-2 py-1 rounded bg-sindri-800 text-sindri-300 hover:bg-sindri-700 hover:text-sindri-200 truncate max-w-xs"
              title={example}
            >
              {example.length > 40 ? example.slice(0, 40) + '...' : example}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function LoadingSpinner() {
  return (
    <svg
      className="animate-spin h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}
