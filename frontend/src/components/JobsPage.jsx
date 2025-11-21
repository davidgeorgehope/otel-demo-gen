import { useState, useEffect } from 'react'
import { api } from '../utils/api'

function JobsPage() {
  const [jobs, setJobs] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedConfig, setSelectedConfig] = useState(null)
  const [showConfigModal, setShowConfigModal] = useState(false)

  const [configJobs, setConfigJobs] = useState([])

  const fetchJobs = async () => {
    try {
      const [jobsData, configJobsData] = await Promise.all([
        api.get('/jobs'),
        api.get('/config-jobs')
      ])
      setJobs(jobsData.jobs)
      setConfigJobs(configJobsData)
    } catch (error) {
      console.error("Failed to fetch jobs:", error)
      setError(`Error fetching jobs: ${error.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStopJob = async (jobId) => {
    try {
      await api.post(`/stop/${jobId}`)
      // Refresh the jobs list with a slight delay to ensure backend processing
      setTimeout(fetchJobs, 300)
    } catch (error) {
      console.error("Failed to stop job:", error)
      setError(`Error stopping job: ${error.message}`)
    }
  }

  const handleRestartJob = async (jobId) => {
    try {
      await api.post(`/restart/${jobId}`)
      // Refresh the jobs list with a slight delay to ensure backend processing
      setTimeout(fetchJobs, 300)
    } catch (error) {
      console.error("Failed to restart job:", error)
      setError(`Error restarting job: ${error.message}`)
    }
  }

  const handleDeleteJob = async (jobId) => {
    if (!confirm('Are you sure you want to delete this job?')) {
      return
    }

    try {
      await api.delete(`/jobs/${jobId}`)
      // Refresh the jobs list with a slight delay to ensure backend processing
      setTimeout(fetchJobs, 300)
    } catch (error) {
      console.error("Failed to delete job:", error)
      setError(`Error deleting job: ${error.message}`)
    }
  }

  const handleViewConfig = (config) => {
    setSelectedConfig(config)
    setShowConfigModal(true)
  }

  const closeConfigModal = () => {
    setShowConfigModal(false)
    setSelectedConfig(null)
  }

  useEffect(() => {
    fetchJobs()
    // Refresh jobs every 3 seconds for more responsive updates
    const interval = setInterval(fetchJobs, 3000)
    return () => clearInterval(interval)
  }, [])

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString()
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
      case 'succeeded':
        return 'bg-green-500'
      case 'stopped':
        return 'bg-gray-500'
      case 'failed':
        return 'bg-red-600'
      case 'pending':
        return 'bg-yellow-500'
      default:
        return 'bg-gray-500'
    }
  }

  const getServiceCount = (config) => {
    return config && config.services ? config.services.length : 0
  }

  const getServiceLanguages = (config) => {
    if (!config || !config.services) return []
    return [...new Set(config.services.map(s => s.language))]
  }

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Telemetry Jobs Section */}
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h2 className="text-2xl font-bold text-white">Active Telemetry Jobs</h2>
          <button
            onClick={fetchJobs}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="bg-red-900 border border-red-500 text-red-300 px-4 py-3 rounded-lg">
            {error}
          </div>
        )}

        {jobs.length === 0 ? (
          <div className="bg-gray-800 p-8 rounded-lg text-center">
            <p className="text-gray-400 text-lg">No telemetry jobs found</p>
            <p className="text-gray-500 mt-2">Create a new job to see it here</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {jobs.map((job) => (
              <div key={job.id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex-1">
                    <div className="mb-2">
                      <h3 className="text-lg font-semibold text-white">{job.description}</h3>
                    </div>
                    <div className="text-sm text-gray-400 space-y-1">
                      <p><span className="font-medium">Job ID:</span> {job.id}</p>
                      <p><span className="font-medium">User:</span> {job.user || 'Not logged in'}</p>
                      <p><span className="font-medium">Created:</span> {formatDate(job.created_at)}</p>
                      <p><span className="font-medium">Services:</span> {getServiceCount(job.config)}</p>
                      <p><span className="font-medium">Languages:</span> {getServiceLanguages(job.config).join(', ')}</p>
                      {job.otlp_endpoint && (
                        <p><span className="font-medium">OTLP Endpoint:</span> {job.otlp_endpoint}</p>
                      )}
                      {job.status === 'failed' && job.error_message && (
                        <div className="mt-2 p-2 bg-red-900/30 border border-red-700/50 rounded">
                          <p className="font-medium text-red-300 text-xs mb-1">Connection Error:</p>
                          <p className="text-xs text-red-200">{job.error_message}</p>
                          {job.failure_count > 0 && (
                            <p className="text-xs text-red-400 mt-1">
                              Consecutive failures: {job.failure_count}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-3">
                    <span className={`px-3 py-1 rounded-full text-xs font-medium text-white whitespace-nowrap uppercase tracking-wide ${getStatusColor(job.status)}`}>
                      {job.status}
                    </span>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => handleViewConfig(job.config)}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors"
                      >
                        View Config
                      </button>
                      {job.status === 'running' && (
                        <button
                          onClick={() => handleStopJob(job.id)}
                          className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-sm transition-colors"
                        >
                          Stop
                        </button>
                      )}
                      {(job.status === 'stopped' || job.status === 'failed') && (
                        <button
                          onClick={() => handleRestartJob(job.id)}
                          className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-sm transition-colors"
                        >
                          {job.status === 'failed' ? 'Restart' : 'Start'}
                        </button>
                      )}
                      <button
                        onClick={() => handleRestartJob(job.id)}
                        className="bg-yellow-600 hover:bg-yellow-700 text-white px-3 py-1 rounded text-sm transition-colors"
                      >
                        Restart
                      </button>
                      <button
                        onClick={() => handleDeleteJob(job.id)}
                        className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded text-sm transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>

                {/* Configuration Summary */}
                <div className="border-t border-gray-700 pt-4">
                  <h4 className="text-sm font-medium text-gray-300 mb-2">Configuration Summary</h4>
                  <div className="bg-gray-900 rounded p-3 text-xs text-gray-400">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div>
                        <span className="font-medium">Services:</span>
                        <ul className="mt-1 space-y-1">
                          {job.config.services && job.config.services.slice(0, 3).map((service, idx) => (
                            <li key={idx} className="text-gray-500">
                              {service.name} ({service.language})
                            </li>
                          ))}
                          {job.config.services && job.config.services.length > 3 && (
                            <li className="text-gray-500">
                              +{job.config.services.length - 3} more
                            </li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <span className="font-medium">Databases:</span>
                        <ul className="mt-1 space-y-1">
                          {job.config.databases && job.config.databases.slice(0, 2).map((db, idx) => (
                            <li key={idx} className="text-gray-500">
                              {db.name} ({db.type})
                            </li>
                          ))}
                          {job.config.databases && job.config.databases.length > 2 && (
                            <li className="text-gray-500">
                              +{job.config.databases.length - 2} more
                            </li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <span className="font-medium">Telemetry:</span>
                        <ul className="mt-1 space-y-1">
                          {job.config.telemetry && (
                            <>
                              <li className="text-gray-500">
                                Rate: {job.config.telemetry.trace_rate}/s
                              </li>
                              <li className="text-gray-500">
                                Error: {(job.config.telemetry.error_rate * 100).toFixed(1)}%
                              </li>
                            </>
                          )}
                        </ul>
                      </div>
                      <div>
                        <span className="font-medium">Queues:</span>
                        <ul className="mt-1 space-y-1">
                          {job.config.message_queues && job.config.message_queues.slice(0, 2).map((mq, idx) => (
                            <li key={idx} className="text-gray-500">
                              {mq.name} ({mq.type})
                            </li>
                          ))}
                          {job.config.message_queues && job.config.message_queues.length > 2 && (
                            <li className="text-gray-500">
                              +{job.config.message_queues.length - 2} more
                            </li>
                          )}
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Config Generation Jobs Section */}
      <div className="space-y-6 pt-8 border-t border-gray-700">
        <h2 className="text-2xl font-bold text-white">Config Generation History</h2>

        {configJobs.length === 0 ? (
          <div className="bg-gray-800 p-8 rounded-lg text-center">
            <p className="text-gray-400 text-lg">No config generation jobs found</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {configJobs.map((job) => (
              <div key={job.job_id} className="bg-gray-800 rounded-lg p-6 border border-gray-700">
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="mb-2">
                      {/* Description is not stored in the job object in main.py for list_config_jobs, 
                           but we can infer or just show ID/Status. 
                           Wait, ConfigGenerationJob HAS description. 
                           Let me check main.py again. 
                           Ah, ConfigJobStatusResponse DOES NOT have description. 
                           I should probably add it to the backend response model if I want to show it.
                           For now, I'll just show ID and Status and Dates.
                       */}
                      <h3 className="text-lg font-semibold text-white">Config Generation {job.job_id.slice(0, 8)}...</h3>
                    </div>
                    <div className="text-sm text-gray-400 space-y-1">
                      <p><span className="font-medium">Job ID:</span> {job.job_id}</p>
                      <p><span className="font-medium">Created:</span> {formatDate(job.created_at)}</p>
                      <p><span className="font-medium">Attempts:</span> {job.attempts} / {job.max_attempts}</p>
                      {job.error_message && (
                        <p className="text-red-400"><span className="font-medium">Error:</span> {job.error_message}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-3">
                    <span className={`px-3 py-1 rounded-full text-xs font-medium text-white whitespace-nowrap uppercase tracking-wide ${getStatusColor(job.status)}`}>
                      {job.status}
                    </span>
                    {job.config && (
                      <button
                        onClick={() => handleViewConfig(job.config)}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors"
                      >
                        View Result
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Config View Modal */}
      {showConfigModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-4xl w-full max-h-[80vh] overflow-hidden">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-white">Job Configuration (JSON)</h3>
              <button
                onClick={closeConfigModal}
                className="text-gray-400 hover:text-white text-xl"
              >
                ×
              </button>
            </div>
            <div className="bg-gray-900 rounded p-4 overflow-auto max-h-[60vh]">
              <pre className="text-sm text-gray-300 whitespace-pre-wrap">
                {JSON.stringify(selectedConfig, null, 2)}
              </pre>
            </div>
            <div className="flex justify-end mt-4">
              <button
                onClick={closeConfigModal}
                className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default JobsPage 