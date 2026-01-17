/**
 * Coverage Visualization Component
 *
 * Displays code coverage data with:
 * - Overall coverage stats (line rate, branch rate)
 * - Package/directory breakdown
 * - File-level detail with covered/uncovered lines
 */

import { useState, useMemo } from 'react'
import { useCoverageDetail } from '../hooks/useApi'
import type { FileCoverage, PackageCoverage } from '../types/api'

interface CoverageViewerProps {
  sessionId: string
}

// Coverage level colors
function getCoverageColor(percentage: number): {
  bg: string
  text: string
  border: string
  bar: string
} {
  if (percentage >= 80) {
    return {
      bg: 'bg-green-900/30',
      text: 'text-green-400',
      border: 'border-green-700',
      bar: 'bg-green-500',
    }
  } else if (percentage >= 50) {
    return {
      bg: 'bg-yellow-900/30',
      text: 'text-yellow-400',
      border: 'border-yellow-700',
      bar: 'bg-yellow-500',
    }
  } else {
    return {
      bg: 'bg-red-900/30',
      text: 'text-red-400',
      border: 'border-red-700',
      bar: 'bg-red-500',
    }
  }
}

// Coverage bar component
function CoverageBar({ percentage }: { percentage: number }) {
  const colors = getCoverageColor(percentage)
  return (
    <div className="w-full h-2 bg-sindri-700 rounded-full overflow-hidden">
      <div
        className={`h-full ${colors.bar} transition-all duration-300`}
        style={{ width: `${Math.min(100, percentage)}%` }}
      />
    </div>
  )
}

// Stat card component
function StatCard({
  label,
  value,
  subvalue,
  percentage,
}: {
  label: string
  value: string | number
  subvalue?: string
  percentage?: number
}) {
  const colors = percentage !== undefined ? getCoverageColor(percentage) : null
  return (
    <div className={`p-4 rounded-lg border ${colors?.bg || 'bg-sindri-800'} ${colors?.border || 'border-sindri-700'}`}>
      <div className="text-sm text-sindri-400">{label}</div>
      <div className={`text-2xl font-bold ${colors?.text || 'text-sindri-100'}`}>
        {value}
        {percentage !== undefined && '%'}
      </div>
      {subvalue && <div className="text-xs text-sindri-500 mt-1">{subvalue}</div>}
    </div>
  )
}

// File row component
function FileRow({
  file,
  isExpanded,
  onToggle,
}: {
  file: FileCoverage
  isExpanded: boolean
  onToggle: () => void
}) {
  const colors = getCoverageColor(file.line_percentage)
  const filename = file.filename.split('/').pop() || file.filename

  return (
    <div className={`border-b border-sindri-700 last:border-b-0`}>
      <div
        className={`flex items-center gap-4 p-3 cursor-pointer hover:bg-sindri-700/50 transition-colors`}
        onClick={onToggle}
      >
        <span className="text-sindri-500">{isExpanded ? '▼' : '▶'}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sindri-200 truncate" title={file.filename}>
              {filename}
            </span>
            <span className="text-xs text-sindri-500 hidden sm:inline">
              {file.filename !== filename && file.filename}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <div className="w-32">
              <CoverageBar percentage={file.line_percentage} />
            </div>
            <span className={`text-sm ${colors.text}`}>
              {file.line_percentage.toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="text-right text-sm">
          <div className={colors.text}>
            {file.lines_covered}/{file.lines_valid}
          </div>
          <div className="text-sindri-500 text-xs">lines</div>
        </div>
      </div>

      {isExpanded && (
        <div className="bg-sindri-900/50 p-3 border-t border-sindri-700">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-sindri-400 mb-1">Covered Lines</div>
              <div className="text-green-400 font-mono text-xs max-h-32 overflow-y-auto">
                {file.covered_lines.length > 0
                  ? file.covered_lines.slice(0, 50).join(', ') +
                    (file.covered_lines.length > 50 ? ` ... (+${file.covered_lines.length - 50} more)` : '')
                  : 'None'}
              </div>
            </div>
            <div>
              <div className="text-sindri-400 mb-1">Uncovered Lines</div>
              <div className="text-red-400 font-mono text-xs max-h-32 overflow-y-auto">
                {file.uncovered_lines.length > 0
                  ? file.uncovered_lines.slice(0, 50).join(', ') +
                    (file.uncovered_lines.length > 50 ? ` ... (+${file.uncovered_lines.length - 50} more)` : '')
                  : 'None'}
              </div>
            </div>
          </div>
          {file.branches_valid > 0 && (
            <div className="mt-3 pt-3 border-t border-sindri-700">
              <span className="text-sindri-400">Branch Coverage: </span>
              <span className={getCoverageColor(file.branch_rate * 100).text}>
                {(file.branch_rate * 100).toFixed(1)}%
              </span>
              <span className="text-sindri-500 ml-2">
                ({file.branches_covered}/{file.branches_valid} branches)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Package section component
function PackageSection({
  pkg,
  isExpanded,
  onToggle,
  expandedFiles,
  onFileToggle,
}: {
  pkg: PackageCoverage
  isExpanded: boolean
  onToggle: () => void
  expandedFiles: Set<string>
  onFileToggle: (filename: string) => void
}) {
  const colors = getCoverageColor(pkg.line_rate * 100)

  return (
    <div className="border border-sindri-700 rounded-lg overflow-hidden mb-4">
      <div
        className={`flex items-center gap-4 p-4 cursor-pointer ${colors.bg} hover:opacity-90 transition-opacity`}
        onClick={onToggle}
      >
        <span className="text-sindri-500 text-lg">{isExpanded ? '▼' : '▶'}</span>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <span className="text-sindri-100 font-medium">{pkg.name || '(root)'}</span>
            <span className="text-sindri-500 text-sm">{pkg.files.length} files</span>
          </div>
          <div className="mt-2 flex items-center gap-3">
            <div className="w-48">
              <CoverageBar percentage={pkg.line_rate * 100} />
            </div>
            <span className={`text-sm font-medium ${colors.text}`}>
              {(pkg.line_rate * 100).toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-lg font-bold ${colors.text}`}>
            {pkg.lines_covered.toLocaleString()}
          </div>
          <div className="text-sindri-500 text-sm">
            / {pkg.lines_valid.toLocaleString()} lines
          </div>
        </div>
      </div>

      {isExpanded && pkg.files.length > 0 && (
        <div className="bg-sindri-800/50">
          {pkg.files.map((file) => (
            <FileRow
              key={file.filename}
              file={file}
              isExpanded={expandedFiles.has(file.filename)}
              onToggle={() => onFileToggle(file.filename)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function CoverageViewer({ sessionId }: CoverageViewerProps) {
  const { data: coverage, isLoading, error } = useCoverageDetail(sessionId)
  const [expandedPackages, setExpandedPackages] = useState<Set<string>>(new Set())
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set())
  const [sortBy, setSortBy] = useState<'name' | 'coverage' | 'size'>('coverage')
  const [filterLowCoverage, setFilterLowCoverage] = useState(false)

  // Sort and filter packages
  const sortedPackages = useMemo(() => {
    if (!coverage) return []

    let packages = [...coverage.packages]

    // Filter low coverage files
    if (filterLowCoverage) {
      packages = packages.map((pkg) => ({
        ...pkg,
        files: pkg.files.filter((f) => f.line_rate < 0.5),
      })).filter((pkg) => pkg.files.length > 0)
    }

    // Sort packages
    switch (sortBy) {
      case 'name':
        packages.sort((a, b) => a.name.localeCompare(b.name))
        break
      case 'coverage':
        packages.sort((a, b) => a.line_rate - b.line_rate)
        break
      case 'size':
        packages.sort((a, b) => b.lines_valid - a.lines_valid)
        break
    }

    // Also sort files within packages
    packages = packages.map((pkg) => ({
      ...pkg,
      files: [...pkg.files].sort((a, b) => {
        switch (sortBy) {
          case 'name':
            return a.filename.localeCompare(b.filename)
          case 'coverage':
            return a.line_rate - b.line_rate
          case 'size':
            return b.lines_valid - a.lines_valid
          default:
            return 0
        }
      }),
    }))

    return packages
  }, [coverage, sortBy, filterLowCoverage])

  const togglePackage = (name: string) => {
    setExpandedPackages((prev) => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
      } else {
        next.add(name)
      }
      return next
    })
  }

  const toggleFile = (filename: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev)
      if (next.has(filename)) {
        next.delete(filename)
      } else {
        next.add(filename)
      }
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-sindri-400">Loading coverage data...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 bg-sindri-800 rounded-lg border border-sindri-700">
        <div className="text-sindri-400 text-center">
          <div className="text-xl mb-2">No coverage data available</div>
          <div className="text-sm text-sindri-500">
            Run tests with coverage enabled to see results here.
          </div>
        </div>
      </div>
    )
  }

  if (!coverage) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Overall Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Line Coverage"
          value={coverage.line_percentage.toFixed(1)}
          subvalue={`${coverage.lines_covered.toLocaleString()} / ${coverage.lines_valid.toLocaleString()} lines`}
          percentage={coverage.line_percentage}
        />
        <StatCard
          label="Branch Coverage"
          value={coverage.branch_percentage.toFixed(1)}
          subvalue={`${coverage.branches_covered.toLocaleString()} / ${coverage.branches_valid.toLocaleString()} branches`}
          percentage={coverage.branch_percentage}
        />
        <StatCard
          label="Files"
          value={coverage.files_count}
          subvalue={`${coverage.packages_count} packages`}
        />
        <StatCard
          label="Source"
          value={coverage.source ? coverage.source.split('/').pop() || 'project' : 'project'}
          subvalue={coverage.timestamp ? new Date(coverage.timestamp).toLocaleString() : undefined}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-sindri-400 text-sm">Sort by:</label>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'name' | 'coverage' | 'size')}
            className="bg-sindri-800 border border-sindri-700 text-sindri-200 rounded px-2 py-1 text-sm"
          >
            <option value="coverage">Coverage (lowest first)</option>
            <option value="name">Name (A-Z)</option>
            <option value="size">Size (largest first)</option>
          </select>
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={filterLowCoverage}
            onChange={(e) => setFilterLowCoverage(e.target.checked)}
            className="rounded bg-sindri-800 border-sindri-700 text-forge-500 focus:ring-forge-500"
          />
          <span className="text-sindri-400 text-sm">Show only low coverage (&lt;50%)</span>
        </label>

        <button
          onClick={() => {
            if (expandedPackages.size > 0) {
              setExpandedPackages(new Set())
              setExpandedFiles(new Set())
            } else {
              setExpandedPackages(new Set(sortedPackages.map((p) => p.name)))
            }
          }}
          className="text-sm text-forge-400 hover:text-forge-300 transition-colors"
        >
          {expandedPackages.size > 0 ? 'Collapse All' : 'Expand All'}
        </button>
      </div>

      {/* Package List */}
      <div>
        {sortedPackages.length === 0 ? (
          <div className="text-center text-sindri-500 py-8">
            {filterLowCoverage
              ? 'No files with coverage below 50%'
              : 'No coverage data available'}
          </div>
        ) : (
          sortedPackages.map((pkg) => (
            <PackageSection
              key={pkg.name}
              pkg={pkg}
              isExpanded={expandedPackages.has(pkg.name)}
              onToggle={() => togglePackage(pkg.name)}
              expandedFiles={expandedFiles}
              onFileToggle={toggleFile}
            />
          ))
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 text-sm text-sindri-400 border-t border-sindri-700 pt-4">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-green-500 rounded" />
          <span>High (&gt;80%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-yellow-500 rounded" />
          <span>Medium (50-80%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-red-500 rounded" />
          <span>Low (&lt;50%)</span>
        </div>
      </div>
    </div>
  )
}

export default CoverageViewer
