import React from 'react'

const ConfigDisplay = ({ configJson, onConfigChange, isGenerating }) => {
  const handleChange = (event) => {
    onConfigChange?.(event.target.value)
  }

  return (
    <div className="bg-gray-800 p-6 rounded-lg shadow-lg h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-semibold text-white">2. Configure Telemetry JSON</h2>
        <span className="text-xs uppercase tracking-wide text-gray-400">
          Paste JSON or use the generator
        </span>
      </div>

      <textarea
        className="flex-1 bg-gray-900 text-sm text-gray-100 font-mono rounded-md p-4 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="Paste or type your scenario configuration JSON here..."
        value={configJson}
        onChange={handleChange}
        spellCheck={false}
        disabled={isGenerating}
      />
    </div>
  )
}

export default ConfigDisplay
