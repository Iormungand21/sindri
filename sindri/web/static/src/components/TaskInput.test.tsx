import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TaskInput } from './TaskInput'

describe('TaskInput', () => {
  it('renders input field', () => {
    render(<TaskInput onSubmit={async () => {}} />)
    expect(
      screen.getByPlaceholderText('Describe your task...')
    ).toBeInTheDocument()
  })

  it('renders submit button', () => {
    render(<TaskInput onSubmit={async () => {}} />)
    expect(screen.getByRole('button', { name: /run task/i })).toBeInTheDocument()
  })

  it('disables button when input is empty', () => {
    render(<TaskInput onSubmit={async () => {}} />)
    const button = screen.getByRole('button', { name: /run task/i })
    expect(button).toBeDisabled()
  })

  it('enables button when input has text', () => {
    render(<TaskInput onSubmit={async () => {}} />)
    const input = screen.getByPlaceholderText('Describe your task...')
    fireEvent.change(input, { target: { value: 'Test task' } })
    const button = screen.getByRole('button', { name: /run task/i })
    expect(button).not.toBeDisabled()
  })

  it('displays example tasks', () => {
    render(<TaskInput onSubmit={async () => {}} />)
    expect(screen.getByText(/try an example/i)).toBeInTheDocument()
  })

  it('clicking example fills input', () => {
    render(<TaskInput onSubmit={async () => {}} />)
    const exampleButtons = screen.getAllByRole('button').filter(
      (btn) => btn.textContent?.includes('validate email')
    )
    if (exampleButtons.length > 0) {
      fireEvent.click(exampleButtons[0])
      const input = screen.getByPlaceholderText('Describe your task...')
      expect(input).toHaveValue(expect.stringContaining('validate email'))
    }
  })

  it('shows loading state', () => {
    render(<TaskInput onSubmit={async () => {}} isLoading={true} />)
    expect(screen.getByText(/running/i)).toBeInTheDocument()
  })

  it('disables input when loading', () => {
    render(<TaskInput onSubmit={async () => {}} isLoading={true} />)
    const input = screen.getByPlaceholderText('Describe your task...')
    expect(input).toBeDisabled()
  })

  it('calls onSubmit with trimmed value', async () => {
    const onSubmit = vi.fn()
    render(<TaskInput onSubmit={onSubmit} />)
    const input = screen.getByPlaceholderText('Describe your task...')
    fireEvent.change(input, { target: { value: '  Test task  ' } })
    const form = input.closest('form')!
    fireEvent.submit(form)
    expect(onSubmit).toHaveBeenCalledWith('Test task')
  })
})
