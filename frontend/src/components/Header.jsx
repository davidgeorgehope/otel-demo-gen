import React from 'react';

const Header = () => {
  // Get current user from localStorage or window for display
  const currentUser = window.forwardedUser || localStorage.getItem('test-forwarded-user') || 'Not logged in';
  
  return (
    <header className="mb-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-4xl font-bold text-white">AI-Powered Observability Demo Generator</h1>
          <p className="text-gray-400">
            Describe a microservices scenario to generate a configuration for a real-time telemetry simulation.
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-500">Current User:</p>
          <p className="text-white font-medium">{currentUser}</p>
        </div>
      </div>
    </header>
  );
};

export default Header; 