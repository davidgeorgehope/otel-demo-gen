import { useState } from 'react'
import yaml from 'js-yaml'
import Header from './components/Header'
import ScenarioForm from './components/ScenarioForm'
import ConfigDisplay from './components/ConfigDisplay'
import Controls from './components/Controls'
import StatusBar from './components/StatusBar'
import JobsPage from './components/JobsPage'
import { API_BASE_URL } from './config'

function App() {
  const [scenario, setScenario] = useState('')
  const [yamlConfig, setYamlConfig] = useState('')
  const [otlpEndpoint, setOtlpEndpoint] = useState('http://localhost:4318')
  const [apiKey, setApiKey] = useState('')
  const [isDemoRunning, setIsDemoRunning] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('create') // 'create' or 'jobs'
  const [currentJobId, setCurrentJobId] = useState(null)

  const handleGenerateConfig = async () => {
    setIsLoading(true)
    setYamlConfig('')
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/generate-config`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ description: scenario }),
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
      const data = await response.json()
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
      const response = await fetch(`${API_BASE_URL}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          config: yamlConfig ? JSON.parse(JSON.stringify(yaml.load(yamlConfig))) : {},
          description: scenario || 'Telemetry Generation Job',
          otlp_endpoint: otlpEndpoint,
          api_key: apiKey,
        }),
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
      const data = await response.json()
      setIsDemoRunning(true)
      setCurrentJobId(data.job_id)
    } catch (error) {
      console.error("Failed to start demo:", error)
      setError(`Error starting demo: ${error.message}`)
    }
  }

  const handleStopDemo = async () => {
    setError('')
    try {
      const response = await fetch(`${API_BASE_URL}/stop`, {
        method: 'POST',
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
      setIsDemoRunning(false)
      setCurrentJobId(null)
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
            onClick={() => setActiveTab('create')}
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

        <StatusBar error={error} isDemoRunning={isDemoRunning} currentJobId={currentJobId} />
      </div>
    </div>
  )
}

export default App
