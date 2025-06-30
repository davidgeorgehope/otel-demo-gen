import { useState } from 'react'
import yaml from 'js-yaml'
import Header from './components/Header'
import ScenarioForm from './components/ScenarioForm'
import ConfigDisplay from './components/ConfigDisplay'
import Controls from './components/Controls'
import StatusBar from './components/StatusBar'

function App() {
  const [scenario, setScenario] = useState('')
  const [yamlConfig, setYamlConfig] = useState('')
  const [otlpEndpoint, setOtlpEndpoint] = useState('http://localhost:4318')
  const [apiKey, setApiKey] = useState('')
  const [isDemoRunning, setIsDemoRunning] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const handleGenerateConfig = async () => {
    setIsLoading(true)
    setYamlConfig('')
    setError('')
    try {
      const response = await fetch('http://localhost:8000/generate-config', {
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
      const response = await fetch('http://localhost:8000/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          config: yamlConfig ? JSON.parse(JSON.stringify(yaml.load(yamlConfig))) : {},
          otlp_endpoint: otlpEndpoint,
          api_key: apiKey,
        }),
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
      setIsDemoRunning(true)
    } catch (error) {
      console.error("Failed to start demo:", error)
      setError(`Error starting demo: ${error.message}`)
    }
  }

  const handleStopDemo = async () => {
    setError('')
    try {
      const response = await fetch('http://localhost:8000/stop', {
        method: 'POST',
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
      setIsDemoRunning(false)
    } catch (error) {
      console.error("Failed to stop demo:", error)
      setError(`Error stopping demo: ${error.message}`)
    }
  }

  return (
    <div className="bg-gray-900 text-white min-h-screen font-sans p-8">
      <div className="max-w-7xl mx-auto">
        <Header />

        <main className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="flex flex-col gap-8">
            <ScenarioForm
              scenario={scenario}
              setScenario={setScenario}
              handleGenerateConfig={handleGenerateConfig}
              isLoading={isLoading}
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
              />
            )}
          </div>
          <div>
            <ConfigDisplay yamlConfig={yamlConfig} />
          </div>
        </main>

        <StatusBar error={error} isDemoRunning={isDemoRunning} />
      </div>
    </div>
  )
}

export default App
