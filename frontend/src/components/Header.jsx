import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

const Header = () => {
  const [currentUser, setCurrentUser] = useState('Loading...');
  const [version, setVersion] = useState('');

  useEffect(() => {
    // Fetch version
    api.get('/version')
      .then(data => setVersion(data.version))
      .catch(err => console.error('Failed to fetch version:', err));

    // Fetch current user
    api.get('/whoami')
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
          <div className="flex items-center gap-3">
            <p className="text-gray-400">
              Describe a microservices scenario to generate a configuration for a real-time telemetry simulation.
            </p>
            {version && (
              <span className="px-2 py-0.5 rounded bg-gray-800 text-xs text-gray-500 border border-gray-700">
                v{version}
              </span>
            )}
          </div>
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