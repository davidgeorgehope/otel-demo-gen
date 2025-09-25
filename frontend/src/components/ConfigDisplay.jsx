import React from 'react';

const ConfigDisplay = ({ configJson }) => {
  if (!configJson) return null;

  return (
    <div className="bg-gray-800 p-6 rounded-lg shadow-lg h-full">
      <h2 className="text-2xl font-semibold mb-4 text-white">2. Review Configuration</h2>
      <pre className="bg-gray-900 p-4 rounded-md overflow-x-auto text-sm text-gray-300 h-[calc(100%-4rem)]">
        <code>{configJson}</code>
      </pre>
    </div>
  );
};

export default ConfigDisplay; 
