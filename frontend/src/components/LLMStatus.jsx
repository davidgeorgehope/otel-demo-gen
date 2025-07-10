import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../config'

function LLMStatus() {
  const [llmConfig, setLlmConfig] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchLLMConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/llm-config`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setLlmConfig(data)
    } catch (error) {
      console.error("Failed to fetch LLM config:", error)
      setError(`Error fetching LLM config: ${error.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchLLMConfig()
  }, [])

  if (isLoading) {
    return (
      <div className="bg-gray-800 p-4 rounded-lg">
        <div className="flex items-center space-x-2">
          <div className="w-4 h-4 bg-gray-500 rounded-full animate-pulse"></div>
          <span className="text-sm text-gray-400">Loading LLM configuration...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900 p-4 rounded-lg border border-red-600">
        <div className="flex items-center space-x-2">
          <div className="w-4 h-4 bg-red-500 rounded-full"></div>
          <span className="text-sm text-red-300">{error}</span>
        </div>
      </div>
    )
  }

  const getStatusColor = (configured) => {
    return configured ? 'bg-green-500' : 'bg-red-500'
  }

  const getStatusText = (configured) => {
    return configured ? 'Configured' : 'Not Configured'
  }

  const getProviderIcon = (provider) => {
    switch (provider) {
      case 'openai':
        return '🤖'
      case 'bedrock':
        return '☁️'
      default:
        return '❓'
    }
  }

  return (
    <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-white">LLM Configuration</h3>
        <button
          onClick={fetchLLMConfig}
          className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
        >
          Refresh
        </button>
      </div>
      
      {llmConfig && (
        <div className="space-y-3">
          <div className="flex items-center space-x-3">
            <div className={`w-3 h-3 rounded-full ${getStatusColor(llmConfig.configured)}`}></div>
            <span className="text-sm font-medium text-white">
              {getProviderIcon(llmConfig.provider)} {llmConfig.provider.toUpperCase()}
            </span>
            <span className={`text-xs px-2 py-1 rounded ${
              llmConfig.configured 
                ? 'bg-green-900 text-green-300' 
                : 'bg-red-900 text-red-300'
            }`}>
              {getStatusText(llmConfig.configured)}
            </span>
          </div>
          
          <div className="text-sm text-gray-400 space-y-1">
            <p><span className="font-medium">Model:</span> {llmConfig.model}</p>
            
            {llmConfig.provider === 'openai' && (
              <p><span className="font-medium">API Key:</span> {llmConfig.details.api_key_set ? '✓ Set' : '✗ Not Set'}</p>
            )}
            
            {llmConfig.provider === 'bedrock' && (
              <>
                <p><span className="font-medium">AWS Access Key:</span> {llmConfig.details.aws_access_key_set ? '✓ Set' : '✗ Not Set'}</p>
                <p><span className="font-medium">AWS Secret Key:</span> {llmConfig.details.aws_secret_key_set ? '✓ Set' : '✗ Not Set'}</p>
                <p><span className="font-medium">AWS Region:</span> {llmConfig.details.aws_region}</p>
              </>
            )}
          </div>
          
          {!llmConfig.configured && (
            <div className="mt-3 p-3 bg-yellow-900 rounded border border-yellow-600">
              <p className="text-sm text-yellow-300">
                ⚠️ LLM provider not configured. Config generation will not work.
                {llmConfig.provider === 'openai' && ' Set OPENAI_API_KEY environment variable.'}
                {llmConfig.provider === 'bedrock' && ' Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables.'}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default LLMStatus 