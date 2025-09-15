import { useState, useEffect } from 'react'
import { api } from '../utils/api'

function ScenariosPage() {
  const [jobs, setJobs] = useState([])
  const [selectedJobId, setSelectedJobId] = useState('')
  const [activeScenarios, setActiveScenarios] = useState([])
  const [templates, setTemplates] = useState([])
  const [description, setDescription] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [generatedScenario, setGeneratedScenario] = useState(null)
  const [justAppliedScenario, setJustAppliedScenario] = useState(null) // Track recently applied scenarios
  const [successMessage, setSuccessMessage] = useState('')

  // Load running jobs and templates on component mount
  useEffect(() => {
    loadJobs()
    loadTemplates()
  }, [])

  // Load active scenarios when job is selected
  useEffect(() => {
    if (selectedJobId) {
      loadActiveScenarios()
      // Set up periodic refresh for active scenarios
      const interval = setInterval(loadActiveScenarios, 5000)
      return () => clearInterval(interval)
    }
  }, [selectedJobId])

  const loadJobs = async () => {
    try {
      const response = await api.get('/jobs')
      const runningJobs = response.jobs.filter(job => job.status === 'running')
      setJobs(runningJobs)

      // Auto-select first running job if none selected
      if (!selectedJobId && runningJobs.length > 0) {
        setSelectedJobId(runningJobs[0].id)
      }
    } catch (err) {
      setError('Failed to load jobs: ' + err.message)
    }
  }

  const loadTemplates = async () => {
    try {
      const response = await api.get('/scenarios/templates')
      setTemplates(response.templates)
    } catch (err) {
      setError('Failed to load templates: ' + err.message)
    }
  }

  const loadActiveScenarios = async () => {
    if (!selectedJobId) return

    try {
      const response = await api.get(`/scenarios/active/${selectedJobId}`)
      setActiveScenarios(response.active_scenarios)
    } catch (err) {
      console.error('Failed to load active scenarios:', err.message)
    }
  }

  const generateScenario = async () => {
    if (!description.trim()) {
      setError('Please enter a scenario description')
      return
    }

    setIsGenerating(true)
    setError('')

    try {
      const response = await api.post('/scenarios/generate', {
        description: description,
        context: {}
      })

      setGeneratedScenario(response.scenario)
    } catch (err) {
      setError('Failed to generate scenario: ' + err.message)
    } finally {
      setIsGenerating(false)
    }
  }

  const applyScenario = async (scenarioData, duration = 5) => {
    if (!selectedJobId) {
      setError('Please select a running job first')
      return
    }

    setIsLoading(true)
    setError('')
    setSuccessMessage('')

    try {
      const response = await api.post(`/scenarios/apply/${selectedJobId}`, {
        scenario: scenarioData,
        duration_minutes: duration
      })

      // Show success message with scenario ID
      setSuccessMessage(`✅ Scenario activated! ID: ${response.scenario_id}`)
      setJustAppliedScenario(response.scenario_id)

      // Clear success message after 3 seconds
      setTimeout(() => {
        setSuccessMessage('')
        setJustAppliedScenario(null)
      }, 3000)

      // Refresh active scenarios
      setTimeout(loadActiveScenarios, 500)
      setGeneratedScenario(null) // Clear generated scenario after applying
    } catch (err) {
      setError('Failed to apply scenario: ' + err.message)
    } finally {
      setIsLoading(false)
    }
  }

  const applyTemplate = async (templateName, duration = null) => {
    if (!selectedJobId) {
      setError('Please select a running job first')
      return
    }

    setIsLoading(true)
    setError('')
    setSuccessMessage('')

    try {
      const response = await api.post(`/scenarios/apply/${selectedJobId}`, {
        template_name: templateName,
        duration_minutes: duration
      })

      // Show success message with template name and scenario ID
      setSuccessMessage(`✅ "${templateName}" activated! ID: ${response.scenario_id}`)
      setJustAppliedScenario(response.scenario_id)

      // Clear success message after 3 seconds
      setTimeout(() => {
        setSuccessMessage('')
        setJustAppliedScenario(null)
      }, 3000)

      // Refresh active scenarios
      setTimeout(loadActiveScenarios, 500)
    } catch (err) {
      setError('Failed to apply template: ' + err.message)
    } finally {
      setIsLoading(false)
    }
  }

  const stopScenario = async (scenarioId) => {
    setIsLoading(true)

    try {
      await api.delete(`/scenarios/${scenarioId}`)
      // Refresh active scenarios
      setTimeout(loadActiveScenarios, 500)
    } catch (err) {
      setError('Failed to stop scenario: ' + err.message)
    } finally {
      setIsLoading(false)
    }
  }

  const formatDuration = (startTime, endTime) => {
    const start = new Date(startTime)
    const end = endTime ? new Date(endTime) : null
    const now = new Date()

    if (end && now > end) {
      return 'Ended'
    }

    const elapsed = Math.floor((now - start) / 1000)
    const minutes = Math.floor(elapsed / 60)
    const seconds = elapsed % 60

    if (end) {
      const remaining = Math.floor((end - now) / 1000)
      const remainingMin = Math.floor(remaining / 60)
      const remainingSec = remaining % 60
      return `${minutes}:${seconds.toString().padStart(2, '0')} / ${remainingMin}:${remainingSec.toString().padStart(2, '0')} remaining`
    }

    return `${minutes}:${seconds.toString().padStart(2, '0')} elapsed`
  }

  return (
    <div className="space-y-8">
      {/* Job Selection */}
      <div className="bg-gray-800 p-6 rounded-lg">
        <h2 className="text-xl font-semibold mb-4 text-white">Select Running Job</h2>

        {jobs.length === 0 ? (
          <p className="text-gray-400">No running jobs found. Start a job first to simulate scenarios.</p>
        ) : (
          <select
            value={selectedJobId}
            onChange={(e) => setSelectedJobId(e.target.value)}
            className="w-full p-3 bg-gray-700 text-white rounded-md border border-gray-600 focus:outline-none focus:border-blue-500"
          >
            {jobs.map(job => (
              <option key={job.id} value={job.id}>
                {job.id} - {job.description} (User: {job.user})
              </option>
            ))}
          </select>
        )}
      </div>

      {/* LLM Scenario Generation */}
      {selectedJobId && (
        <div className="bg-gray-800 p-6 rounded-lg">
          <h2 className="text-xl font-semibold mb-4 text-white">🤖 Generate Custom Scenario</h2>

          <div className="space-y-4">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the outage scenario you want to simulate...
Examples:
- 'Payment database becomes slow and starts timing out'
- 'API gateway starts returning 500 errors for 25% of requests'
- 'User service experiences high memory pressure'"
              rows={4}
              className="w-full p-3 bg-gray-700 text-white rounded-md border border-gray-600 focus:outline-none focus:border-blue-500 placeholder-gray-400"
            />

            <button
              onClick={generateScenario}
              disabled={isGenerating || !description.trim()}
              className={`px-6 py-2 rounded-md text-white font-medium transition-colors ${
                isGenerating || !description.trim()
                  ? 'bg-gray-600 cursor-not-allowed'
                  : 'bg-purple-600 hover:bg-purple-700'
              }`}
            >
              {isGenerating ? 'Generating...' : 'Generate Scenario'}
            </button>
          </div>

          {/* Generated Scenario Display */}
          {generatedScenario && (
            <div className="mt-6 p-4 bg-gray-700 rounded-md">
              <h3 className="font-semibold text-white mb-2">Generated Scenario</h3>
              <div className="text-sm text-gray-300 mb-4">
                <p><strong>Type:</strong> {generatedScenario.type}</p>
                <p><strong>Target Services:</strong> {generatedScenario.target_services.join(', ')}</p>
                <p><strong>Parameters:</strong></p>
                <ul className="ml-4">
                  {generatedScenario.parameters.map((param, idx) => (
                    <li key={idx}>
                      {param.key}: {param.value} {param.unit || ''}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex space-x-2">
                <button
                  onClick={() => applyScenario(generatedScenario, 3)}
                  disabled={isLoading}
                  className={`px-4 py-2 text-white text-sm rounded-md transition-all ${
                    isLoading
                      ? 'bg-gray-500 cursor-not-allowed opacity-50'
                      : 'bg-red-600 hover:bg-red-700'
                  }`}
                >
                  {isLoading ? 'Activating...' : 'Apply (3 min)'}
                </button>
                <button
                  onClick={() => applyScenario(generatedScenario, 5)}
                  disabled={isLoading}
                  className={`px-4 py-2 text-white text-sm rounded-md transition-all ${
                    isLoading
                      ? 'bg-gray-500 cursor-not-allowed opacity-50'
                      : 'bg-orange-600 hover:bg-orange-700'
                  }`}
                >
                  {isLoading ? 'Activating...' : 'Apply (5 min)'}
                </button>
                <button
                  onClick={() => setGeneratedScenario(null)}
                  disabled={isLoading}
                  className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white text-sm rounded-md disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Quick Scenario Templates */}
      {selectedJobId && templates.length > 0 && (
        <div className="bg-gray-800 p-6 rounded-lg">
          <h2 className="text-xl font-semibold mb-4 text-white">🔧 Quick Scenario Templates</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {templates.map((template) => (
              <div key={template.name} className="bg-gray-700 p-4 rounded-md">
                <h3 className="font-semibold text-white mb-2">{template.name}</h3>
                <p className="text-sm text-gray-300 mb-2">{template.description}</p>
                <p className="text-xs text-gray-400 mb-3">Category: {template.category}</p>

                <div className="flex space-x-2">
                  <button
                    onClick={() => applyTemplate(template.name)}
                    disabled={isLoading}
                    className={`px-3 py-1 text-white text-sm rounded transition-all ${
                      isLoading
                        ? 'bg-gray-500 cursor-not-allowed opacity-50'
                        : 'bg-blue-600 hover:bg-blue-700'
                    }`}
                  >
                    {isLoading ? 'Activating...' : 'Apply Default'}
                  </button>
                  <button
                    onClick={() => applyTemplate(template.name, 2)}
                    disabled={isLoading}
                    className={`px-3 py-1 text-white text-sm rounded transition-all ${
                      isLoading
                        ? 'bg-gray-500 cursor-not-allowed opacity-50'
                        : 'bg-yellow-600 hover:bg-yellow-700'
                    }`}
                  >
                    {isLoading ? 'Activating...' : '2 min'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Scenarios */}
      {selectedJobId && (
        <div className="bg-gray-800 p-6 rounded-lg">
          <h2 className="text-xl font-semibold mb-4 text-white">📈 Active Scenarios</h2>

          {activeScenarios.length === 0 ? (
            <p className="text-gray-400">No active scenarios for this job.</p>
          ) : (
            <div className="space-y-3">
              {activeScenarios.map((scenario) => {
                const isJustApplied = justAppliedScenario === scenario.id;
                return (
                  <div
                    key={scenario.id}
                    className={`p-4 rounded-md flex justify-between items-center transition-all ${
                      isJustApplied
                        ? 'bg-green-800 border-2 border-green-600 animate-pulse'
                        : 'bg-gray-700'
                    }`}
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-white">{scenario.description}</h3>
                        {isJustApplied && (
                          <span className="bg-green-600 text-green-100 text-xs px-2 py-1 rounded-full">
                            Just Applied!
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-300 mt-1">
                        <span className="inline-block mr-4">
                          ID: {scenario.id}
                        </span>
                        <span className="inline-block mr-4">
                          Type: {scenario.modification.type}
                        </span>
                        <span className="inline-block mr-4">
                          Services: {scenario.modification.target_services.join(', ')}
                        </span>
                        <span className="inline-block">
                          {formatDuration(scenario.started_at, scenario.ends_at)}
                        </span>
                      </div>
                    </div>

                    <button
                      onClick={() => stopScenario(scenario.id)}
                      disabled={isLoading}
                      className={`px-3 py-1 text-white text-sm rounded transition-all ${
                        isLoading
                          ? 'bg-gray-500 cursor-not-allowed opacity-50'
                          : 'bg-red-600 hover:bg-red-700'
                      }`}
                    >
                      {isLoading ? 'Stopping...' : 'Stop'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Success Message */}
      {successMessage && (
        <div className="bg-green-900 border border-green-600 text-green-200 p-4 rounded-lg animate-pulse">
          {successMessage}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-900 border border-red-600 text-red-200 p-4 rounded-lg">
          {error}
        </div>
      )}
    </div>
  )
}

export default ScenariosPage