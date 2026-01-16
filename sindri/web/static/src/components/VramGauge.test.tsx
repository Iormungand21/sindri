import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { VramGauge } from './VramGauge'

describe('VramGauge', () => {
  it('renders usage values correctly', () => {
    render(<VramGauge used={8} total={16} models={[]} />)
    expect(screen.getByText('8.0 / 16.0 GB')).toBeInTheDocument()
  })

  it('calculates percentage correctly', () => {
    render(<VramGauge used={8} total={16} models={[]} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('displays loaded models', () => {
    render(
      <VramGauge
        used={5}
        total={16}
        models={['qwen2.5-coder:7b', 'llama3.1:8b']}
      />
    )
    expect(screen.getByText('qwen2.5-coder:7b')).toBeInTheDocument()
    expect(screen.getByText('llama3.1:8b')).toBeInTheDocument()
  })

  it('shows model count', () => {
    render(
      <VramGauge
        used={5}
        total={16}
        models={['model1', 'model2']}
      />
    )
    expect(screen.getByText('Loaded Models (2)')).toBeInTheDocument()
  })

  it('shows empty state when no models', () => {
    render(<VramGauge used={0} total={16} models={[]} />)
    expect(screen.getByText('No models loaded')).toBeInTheDocument()
  })

  it('shows warning for high VRAM usage', () => {
    render(<VramGauge used={14} total={16} models={[]} />)
    expect(
      screen.getByText(/High VRAM usage/i)
    ).toBeInTheDocument()
  })

  it('handles zero total VRAM gracefully', () => {
    render(<VramGauge used={0} total={0} models={[]} />)
    expect(screen.getByText('0%')).toBeInTheDocument()
  })
})
