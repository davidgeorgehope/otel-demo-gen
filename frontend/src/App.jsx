import { useState, useEffect } from 'react'
import yaml from 'js-yaml'
import Header from './components/Header'
import ScenarioForm from './components/ScenarioForm'
import ConfigDisplay from './components/ConfigDisplay'
import Controls from './components/Controls'
import StatusBar from './components/StatusBar'
import JobsPage from './components/JobsPage'
import { api } from './utils/api'

function App() {
  const [scenario, setScenario] = useState('')
  const [yamlConfig, setYamlConfig] = useState('')
  const [otlpEndpoint, setOtlpEndpoint] = useState('http://localhost:4318')
  const [apiKey, setApiKey] = useState('')
  const [authType, setAuthType] = useState('ApiKey')
  const [isDemoRunning, setIsDemoRunning] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('create') // 'create' or 'jobs'
  const [currentJobId, setCurrentJobId] = useState(null)
  const [currentJobStatus, setCurrentJobStatus] = useState(null)
  const [currentJobError, setCurrentJobError] = useState(null)

  // Sync state with backend status
  const checkStatus = async () => {
    try {
      const statusData = await api.get('/status')
      setIsDemoRunning(statusData.running)
      setCurrentJobId(statusData.job_id)
      
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

  const handleGenerateConfig = async () => {
    setIsLoading(true)
    setYamlConfig('')
    setError('')
    try {
      const data = await api.post('/generate-config', { description: scenario })
      setYamlConfig(data.yaml)
    } catch (error) {
      console.error("Failed to generate config:", error)
      setError(`Error generating config: ${error.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStartDemo = async () => {
    setError('')
    try {
      // Always create a new job - support multiple concurrent jobs
      const data = await api.post('/start', {
        config: yamlConfig ? JSON.parse(JSON.stringify(yaml.load(yamlConfig))) : {},
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

    return (
      <main className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="flex flex-col gap-8">
          <ScenarioForm
            scenario={scenario}
            setScenario={setScenario}
            handleGenerateConfig={handleGenerateConfig}
            isLoading={isLoading}
            setYamlConfig={setYamlConfig}
          />
          {yamlConfig && (
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
          <ConfigDisplay yamlConfig={yamlConfig} />
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
