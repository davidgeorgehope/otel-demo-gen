import React from 'react';
import LLMStatus from './LLMStatus';
import { API_BASE_URL } from '../config';

const ScenarioForm = ({
  scenario,
  setScenario,
  handleGenerateConfig,
  isLoading,
  setConfigJson,
  configJobId,
  configJobStatus
}) => {
  const handleLoadTestConfig = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/test-config`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      // Use the passed setter to hydrate the editor with example JSON
      if (data.config_json) {
        setConfigJson(data.config_json)
      } else if (data.config) {
        setConfigJson(JSON.stringify(data.config, null, 2))
      }
      // Also set a default scenario description
      setScenario("Test scenario: 3-tier web application with TypeScript frontend, Java API gateway, and Python user service")
    } catch (error) {
      console.error("Failed to load test config:", error)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-800 p-6 rounded-lg shadow-lg">
        <h2 className="text-2xl font-semibold mb-4 text-white">1. Describe Your Scenario</h2>
        <textarea
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          placeholder="Describe your microservices architecture (e.g., 'E-commerce platform with user service, product catalog, payment processing, and notification system')"
          className="w-full h-32 p-3 bg-gray-700 rounded-md border border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-200 placeholder-gray-400"
          disabled={isLoading}
        />
        <div className="mt-4 flex gap-3">
          <button
            onClick={handleGenerateConfig}
            disabled={isLoading || !scenario.trim()}
            className="flex-1 px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-200 font-semibold"
          >
            {isLoading ? 'Generating...' : 'Generate Configuration'}
          </button>
          <button
            onClick={handleLoadTestConfig}
            disabled={isLoading}
            className="px-6 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-200 font-semibold"
          >
            Load Test Config
          </button>
        </div>
        {configJobId && (
          <div className="mt-2 text-sm text-gray-400">
            <span className="font-medium text-gray-300">Config job:</span>{' '}
            <span className="font-mono">{configJobId}</span>
            {configJobStatus && (
              <span className="ml-2 capitalize">[{configJobStatus}]</span>
            )}
          </div>
        )}
      </div>
      
      <LLMStatus />
    </div>
  );
};

export default ScenarioForm; 
