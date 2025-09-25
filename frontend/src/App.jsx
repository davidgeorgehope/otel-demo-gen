import { useState, useEffect, useRef } from 'react'
import Header from './components/Header'
import ScenarioForm from './components/ScenarioForm'
import ConfigDisplay from './components/ConfigDisplay'
import Controls from './components/Controls'
import StatusBar from './components/StatusBar'
import JobsPage from './components/JobsPage'
import ScenariosPage from './components/ScenariosPage'
import { api } from './utils/api'

function App() {
  const [scenario, setScenario] = useState('')
  const [configJson, setConfigJsonState] = useState('')
  const [otlpEndpoint, setOtlpEndpoint] = useState('http://localhost:4318')
  const [apiKey, setApiKey] = useState('')
  const [authType, setAuthType] = useState('ApiKey')
  const [isDemoRunning, setIsDemoRunning] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('create') // 'create', 'jobs', or 'scenarios'
  const [currentJobId, setCurrentJobId] = useState(null)
  const [currentJobStatus, setCurrentJobStatus] = useState(null)
  const [currentJobError, setCurrentJobError] = useState(null)
  const [configJobId, setConfigJobId] = useState(null)
  const [configJobStatus, setConfigJobStatus] = useState(null)
  const activeConfigJobRef = useRef(null)
  const configSourceRef = useRef('none')

  const updateConfigJson = (value, source = 'manual') => {
    configSourceRef.current = source
    setConfigJsonState(value)
  }

  // Sync state with backend status
  const checkStatus = async () => {
    try {
      const statusData = await api.get('/status')
      setIsDemoRunning(statusData.running)
      setCurrentJobId(statusData.job_id)
      if (statusData.running && statusData.config) {
        updateConfigJson(JSON.stringify(statusData.config, null, 2), 'status')
      } else if (!statusData.running && configSourceRef.current === 'status') {
        updateConfigJson('', 'none')
      }
      
      // If we have a job ID, get detailed job info for error handling
      if (statusData.job_id) {
        try {
          const jobData = await api.get(`/jobs/${statusData.job_id}`)
          setCurrentJobStatus(jobData.status)
          setCurrentJobError(jobData.error_message)
        } catch (jobError) {
          console.debug('Job status check failed:', jobError.message)
        }
      } else {
        setCurrentJobStatus(null)
        setCurrentJobError(null)
      }
    } catch (error) {
      // Silently handle error - status endpoint might not be available
      console.debug('Status check failed:', error.message)
    }
  }

  useEffect(() => {
    // Check status on mount
    checkStatus()
    
    // Check status every 5 seconds to stay in sync
    const interval = setInterval(checkStatus, 5000)
    
    return () => clearInterval(interval)
  }, [])

  const pollConfigGenerationJob = async (jobId) => {
    const pollIntervalMs = 2000
    const maxWaitMs = 300000 // 5 minutes timeout for config generation
    let elapsedMs = 0

    while (true) {
      if (activeConfigJobRef.current !== jobId) {
        return
      }

      try {
        const status = await api.get(`/generate-config/${jobId}`)
        setConfigJobStatus(status.status)

        if (status.status === 'succeeded') {
          if (status.config_json) {
            updateConfigJson(status.config_json, 'generator')
          } else if (status.config) {
            updateConfigJson(JSON.stringify(status.config, null, 2), 'generator')
          }
          setError('')
          setIsLoading(false)
          activeConfigJobRef.current = null
          return
        }

        if (status.status === 'failed') {
          const message = status.error_message || 'Config generation failed.'
          setError(`Error generating config: ${message}`)
          setIsLoading(false)
          activeConfigJobRef.current = null
          return
        }
      } catch (pollError) {
        console.error('Failed to fetch config generation status:', pollError)
        setError(`Error checking config status: ${pollError.message}`)
        setConfigJobStatus('failed')
        setIsLoading(false)
        activeConfigJobRef.current = null
        return
      }

      if (elapsedMs >= maxWaitMs) {
        setError('Timed out waiting for config generation. Please try again.')
        setConfigJobStatus('failed')
        setIsLoading(false)
        activeConfigJobRef.current = null
        return
      }

      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs))
      elapsedMs += pollIntervalMs
    }
  }

  const handleGenerateConfig = async () => {
    setIsLoading(true)
    updateConfigJson('', 'none')
    setError('')
    setConfigJobStatus('pending')
    setConfigJobId(null)

    try {
      const data = await api.post('/generate-config', { description: scenario })
      const jobId = data.job_id
      setConfigJobStatus(data.status || 'pending')
      setConfigJobId(jobId)
      activeConfigJobRef.current = jobId
      await pollConfigGenerationJob(jobId)
    } catch (error) {
      console.error('Failed to start config generation job:', error)
      setError(`Error generating config: ${error.message}`)
      setIsLoading(false)
      setConfigJobStatus('failed')
      activeConfigJobRef.current = null
    }
  }

  const handleStartDemo = async () => {
    setError('')
    try {
      let parsedConfig = {}
      if (configJson) {
        try {
          parsedConfig = JSON.parse(configJson)
        } catch (parseError) {
          console.error('Invalid JSON config supplied:', parseError)
          setError('Configuration JSON is invalid. Please fix formatting or regenerate.')
          return
        }
      }

      // Always create a new job - support multiple concurrent jobs
      const data = await api.post('/start', {
        config: parsedConfig,
        description: scenario || 'Telemetry Generation Job',
        otlp_endpoint: otlpEndpoint,
        api_key: apiKey,
        auth_type: authType,
      })
      setIsDemoRunning(true)
      setCurrentJobId(data.job_id)
      // Force a status check to ensure UI is in sync
      setTimeout(checkStatus, 500)
    } catch (error) {
      console.error("Failed to start demo:", error)
      setError(`Error starting demo: ${error.message}`)
    }
  }

  const handleStopDemo = async () => {
    setError('')
    try {
      await api.post('/stop')
      setIsDemoRunning(false)
      setCurrentJobId(null)
      // Force a status check to ensure UI is in sync
      setTimeout(checkStatus, 500)
    } catch (error) {
      console.error("Failed to stop demo:", error)
      setError(`Error stopping demo: ${error.message}`)
    }
  }

  const renderTabContent = () => {
    if (activeTab === 'jobs') {
      return <JobsPage />
    }

    if (activeTab === 'scenarios') {
      return <ScenariosPage />
    }

    return (
      <main className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="flex flex-col gap-8">
          <ScenarioForm
            scenario={scenario}
            setScenario={setScenario}
            handleGenerateConfig={handleGenerateConfig}
            isLoading={isLoading}
            setConfigJson={updateConfigJson}
            configJobId={configJobId}
            configJobStatus={configJobStatus}
          />
          {configJson && (
             <Controls
              otlpEndpoint={otlpEndpoint}
              setOtlpEndpoint={setOtlpEndpoint}
              apiKey={apiKey}
              setApiKey={setApiKey}
              authType={authType}
              setAuthType={setAuthType}
              isDemoRunning={isDemoRunning}
              handleStartDemo={handleStartDemo}
              handleStopDemo={handleStopDemo}
              currentJobId={currentJobId}
            />
          )}
        </div>
        <div>
          <ConfigDisplay configJson={configJson} />
        </div>
      </main>
    )
  }

  return (
    <div className="bg-gray-900 text-white min-h-screen font-sans p-8">
      <div className="max-w-7xl mx-auto">
        <Header />

        {/* Navigation Tabs */}
        <div className="flex space-x-1 bg-gray-800 p-1 rounded-lg mb-8">
          <button
            onClick={() => {
              setActiveTab('create')
              // Refresh status when switching back to create tab
              setTimeout(checkStatus, 100)
            }}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'create'
                ? 'bg-blue-600 text-white'
                : 'text-gray-300 hover:text-white hover:bg-gray-700'
            }`}
          >
            Create New Job
          </button>
          <button
            onClick={() => setActiveTab('jobs')}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'jobs'
                ? 'bg-blue-600 text-white'
                : 'text-gray-300 hover:text-white hover:bg-gray-700'
            }`}
          >
            Manage Jobs
          </button>
          <button
            onClick={() => setActiveTab('scenarios')}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
              activeTab === 'scenarios'
                ? 'bg-blue-600 text-white'
                : 'text-gray-300 hover:text-white hover:bg-gray-700'
            }`}
          >
            Simulate Outages
          </button>
        </div>

        {renderTabContent()}

        <StatusBar 
          error={error} 
          isDemoRunning={isDemoRunning} 
          currentJobId={currentJobId}
          jobStatus={currentJobStatus}
          jobError={currentJobError}
        />
      </div>
    </div>
  )
}

export default App
