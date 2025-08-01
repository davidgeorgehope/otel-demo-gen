import React from 'react';

const StatusBar = ({ isDemoRunning, error, currentJobId, jobStatus, jobError }) => {
  return (
    <div className="mt-8">
      {error && (
        <div className="bg-red-900 border border-red-700 text-red-200 p-4 rounded-lg mb-4">
          <p className="font-bold">An error occurred:</p>
          <p>{error}</p>
        </div>
      )}
      
      {/* Job-specific error display */}
      {jobStatus === 'failed' && jobError && (
        <div className="bg-red-900 border border-red-700 text-red-200 p-4 rounded-lg mb-4">
          <div className="flex items-center mb-2">
            <span className="text-red-400 mr-2">❌</span>
            <p className="font-bold">Job Failed - OTLP Connection Error</p>
          </div>
          <p className="text-sm mb-2">{jobError}</p>
          {currentJobId && (
             <p className="text-xs text-red-300">
               Job ID: <span className="font-mono">{currentJobId}</span>
             </p>
          )}
        </div>
      )}

      {isDemoRunning && jobStatus !== 'failed' && (
        <div className="bg-green-900 border border-green-700 text-green-200 p-4 rounded-lg flex items-center">
          <span className="relative flex h-3 w-3 mr-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
          </span>
          <div>
            <p className="font-semibold">Demo is running...</p>
            {currentJobId && (
              <p className="text-sm text-green-300 mt-1">
                Job ID: <span className="font-mono">{currentJobId}</span>
              </p>
            )}
          </div>
        </div>
      )}
      
      {!isDemoRunning && jobStatus === 'stopped' && (
        <div className="bg-gray-800 border border-gray-600 text-gray-200 p-4 rounded-lg flex items-center">
          <span className="text-gray-400 mr-3">⏸️</span>
          <div>
            <p className="font-semibold">Demo stopped</p>
            {currentJobId && (
              <p className="text-sm text-gray-400 mt-1">
                Job ID: <span className="font-mono">{currentJobId}</span>
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default StatusBar; 