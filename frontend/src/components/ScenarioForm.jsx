import React from 'react';

const ScenarioForm = ({ scenario, setScenario, handleGenerateConfig, isLoading }) => {
  return (
    <div className="bg-gray-800 p-6 rounded-lg shadow-lg">
      <h2 className="text-2xl font-semibold mb-4 text-white">1. Describe Your Scenario</h2>
      <textarea
        className="w-full h-32 p-3 bg-gray-700 rounded-md border border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-200"
        placeholder="e.g., a financial services app with 10 microservices, Postgres and Redis databases, and a Kafka queue"
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        disabled={isLoading}
      />
      <button
        onClick={handleGenerateConfig}
        disabled={isLoading || !scenario.trim()}
        className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-200 font-semibold"
      >
        {isLoading ? 'Generating...' : 'Generate Config'}
      </button>
    </div>
  );
};

export default ScenarioForm; 