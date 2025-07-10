import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../config'

function JobsPage() {
  const [jobs, setJobs] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchJobs = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/jobs`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      setJobs(data.jobs)
    } catch (error) {
      console.error("Failed to fetch jobs:", error)
      setError(`Error fetching jobs: ${error.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleStopJob = async (jobId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/stop/${jobId}`, {
        method: 'POST',
      })
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      // Refresh the jobs list
      fetchJobs()
    } catch (error) {
      console.error("Failed to stop job:", error)
      setError(`Error stopping job: ${error.message}`)
    }
  }

  const handleDeleteJob = async (jobId) => {
    if (!confirm('Are you sure you want to delete this job?')) {
      return
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
        method: 'DELETE',
      })
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      // Refresh the jobs list
      fetchJobs()
    } catch (error) {
      console.error("Failed to delete job:", error)
      setError(`Error deleting job: ${error.message}`)
    }
  }

  useEffect(() => {
    fetchJobs()
    // Refresh jobs every 5 seconds
    const interval = setInterval(fetchJobs, 5000)
    return () => clearInterval(interval)
  }, [])

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString()
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'bg-green-500'
      case 'stopped':
        return 'bg-red-500'
      default:
        return 'bg-gray-500'
    }
  }

  const getServiceCount = (config) => {
    return config.services ? config.services.length : 0
  }

  const getServiceLanguages = (config) => {
    if (!config.services) return []
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
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-white">{job.description}</h3>
                    <span className={`px-2 py-1 rounded text-xs font-medium text-white ${getStatusColor(job.status)}`}>
                      {job.status}
                    </span>
                  </div>
                  <div className="text-sm text-gray-400 space-y-1">
                    <p><span className="font-medium">Job ID:</span> {job.id}</p>
                    <p><span className="font-medium">Created:</span> {formatDate(job.created_at)}</p>
                    <p><span className="font-medium">Services:</span> {getServiceCount(job.config)}</p>
                    <p><span className="font-medium">Languages:</span> {getServiceLanguages(job.config).join(', ')}</p>
                    {job.otlp_endpoint && (
                      <p><span className="font-medium">OTLP Endpoint:</span> {job.otlp_endpoint}</p>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  {job.status === 'running' && (
                    <button
                      onClick={() => handleStopJob(job.id)}
                      className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-sm transition-colors"
                    >
                      Stop
                    </button>
                  )}
                  <button
                    onClick={() => handleDeleteJob(job.id)}
                    className="bg-gray-600 hover:bg-gray-700 text-white px-3 py-1 rounded text-sm transition-colors"
                  >
                    Delete
                  </button>
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
  )
}

export default JobsPage 