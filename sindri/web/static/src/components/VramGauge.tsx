/**
 * VramGauge - Visual representation of GPU memory usage
 */

interface VramGaugeProps {
  used: number
  total: number
  models: string[]
}

export function VramGauge({ used, total, models }: VramGaugeProps) {
  const percentage = total > 0 ? (used / total) * 100 : 0
  const isWarning = percentage > 60 && percentage <= 85
  const isCritical = percentage > 85

  const barColor = isCritical
    ? 'bg-red-500'
    : isWarning
      ? 'bg-yellow-500'
      : 'bg-green-500'

  const textColor = isCritical
    ? 'text-red-400'
    : isWarning
      ? 'text-yellow-400'
      : 'text-green-400'

  return (
    <div className="space-y-4">
      {/* Gauge bar */}
      <div>
        <div className="flex justify-between text-sm mb-2">
          <span className={textColor}>
            {used.toFixed(1)} / {total.toFixed(1)} GB
          </span>
          <span className={textColor}>{percentage.toFixed(0)}%</span>
        </div>
        <div className="h-4 bg-sindri-700 rounded-full overflow-hidden">
          <div
            className={`h-full ${barColor} transition-all duration-300 rounded-full`}
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
        </div>
      </div>

      {/* Loaded models */}
      <div>
        <p className="text-xs text-sindri-500 mb-2">
          Loaded Models ({models.length})
        </p>
        {models.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {models.map((model) => (
              <span
                key={model}
                className="text-xs px-2 py-0.5 rounded bg-sindri-700 text-sindri-300"
              >
                {model}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-sindri-500 italic">No models loaded</p>
        )}
      </div>

      {/* Status indicator */}
      {isCritical && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          High VRAM usage - consider unloading models
        </div>
      )}
    </div>
  )
}
