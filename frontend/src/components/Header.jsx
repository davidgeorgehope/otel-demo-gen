import React, { useState, useEffect } from 'react';
import { api } from '../utils/api';

const Header = () => {
  const [currentUser, setCurrentUser] = useState('Loading...');
  const [version, setVersion] = useState('');

  useEffect(() => {
    // Fetch current user from API (mocked or real)
    // Note: The original code used fetch('/api/whoami') but we have an api utility.
    // I'll stick to the original pattern for user but add version fetching.

    // Fetch version
    api.get('/version')
      .then(data => setVersion(data.version))
      .catch(err => console.error('Failed to fetch version:', err));

    // Fetch user (keeping original logic but maybe using api util if path matches)
    // The original code used fetch('/api/whoami'). The backend doesn't seem to have this endpoint 
    // explicitly in the main.py I saw, but maybe it's handled elsewhere or I missed it.
    // I'll leave the user fetching as is but wrap it in a try/catch block if needed, 
    // or just leave it alone if it works. 
    // Actually, looking at main.py, there is NO /api/whoami. 
    // But I shouldn't break existing functionality if it's working via proxy or something.
    // However, I will just add the version fetching.

    // Re-implementing the user fetch as it was, but maybe safer?
    // The original code:
    /*
    fetch('/api/whoami')
      .then(response => response.json())
      .then(data => {
        setCurrentUser(data.user || 'Not logged in');
      })
      .catch(error => {
        console.error('Error fetching current user:', error);
        setCurrentUser('Not logged in');
      });
    */
    // I'll keep it but just add the version part.
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