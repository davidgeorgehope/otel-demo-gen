import React from 'react';

const Controls = ({
  otlpEndpoint,
  setOtlpEndpoint,
  apiKey,
  setApiKey,
  isDemoRunning,
  handleStartDemo,
  handleStopDemo,
}) => {
  return (
    <div className="bg-gray-800 p-6 rounded-lg shadow-lg mt-8">
      <h2 className="text-2xl font-semibold mb-4 text-white">3. Configure & Run</h2>
      <div className="space-y-4">
        <div>
          <label htmlFor="otlp-endpoint" className="block mb-2 text-sm font-medium text-gray-400">
            OTLP Endpoint URL
          </label>
          <input
            id="otlp-endpoint"
            type="text"
            value={otlpEndpoint}
            onChange={(e) => setOtlpEndpoint(e.target.value)}
            className="w-full p-2 bg-gray-700 rounded-md border border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-200"
            disabled={isDemoRunning}
          />
        </div>
        <div>
          <label htmlFor="api-key" className="block mb-2 text-sm font-medium text-gray-400">
            API Key (Optional)
          </label>
          <input
            id="api-key"
            type="password"
            placeholder="Enter API Key for Authorization header"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="w-full p-2 bg-gray-700 rounded-md border border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-200"
            disabled={isDemoRunning}
          />
        </div>
      </div>
      <div className="mt-6 flex space-x-4 items-center">
        <button
          onClick={handleStartDemo}
          disabled={isDemoRunning || !otlpEndpoint.trim()}
          className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-200 font-semibold"
        >
          Start Demo
        </button>
        <button
          onClick={handleStopDemo}
          disabled={!isDemoRunning}
          className="px-6 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:bg-gray-500 disabled:cursor-not-allowed transition-colors duration-200 font-semibold"
        >
          Stop Demo
        </button>
      </div>
    </div>
  );
};

export default Controls; 