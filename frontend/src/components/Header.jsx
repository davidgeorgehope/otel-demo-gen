import React, { useState, useEffect } from 'react';

const Header = () => {
  const [currentUser, setCurrentUser] = useState('Loading...');
  
  useEffect(() => {
    // Fetch current user from API
    fetch('/api/whoami')
      .then(response => response.json())
      .then(data => {
        setCurrentUser(data.user || 'Not logged in');
      })
      .catch(error => {
        console.error('Error fetching current user:', error);
        setCurrentUser('Not logged in');
      });
  }, []);
  
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