import { API_BASE_URL } from '../config'

/**
 * For testing purposes, you can set a test user in the browser console:
 * localStorage.setItem('test-forwarded-user', 'test-user@example.com')
 * 
 * To clear the test user:
 * localStorage.removeItem('test-forwarded-user')
 */

/**
 * Get the user from X-Forwarded-User header (set by proxy)
 * Returns null if not available (for client-side calls)
 */
function getForwardedUser() {
  // In a real proxy setup, this header would be available server-side
  // For client-side, we'll check if it's available in the window
  // Or from localStorage for testing purposes
  return window.forwardedUser || localStorage.getItem('test-forwarded-user') || null
}

/**
 * Create headers object with X-Forwarded-User if available
 */
function createHeaders(additionalHeaders = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...additionalHeaders
  }
  
  const forwardedUser = getForwardedUser()
  if (forwardedUser) {
    headers['X-Forwarded-User'] = forwardedUser
  }
  
  return headers
}

/**
 * Make an API request with proper headers
 */
export async function apiRequest(endpoint, options = {}) {
  const config = {
    ...options,
    headers: createHeaders(options.headers)
  }
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, config)
  
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
  }
  
  return response.json()
}

/**
 * API convenience methods
 */
export const api = {
  get: (endpoint) => apiRequest(endpoint),
  post: (endpoint, data) => apiRequest(endpoint, { method: 'POST', body: JSON.stringify(data) }),
  delete: (endpoint) => apiRequest(endpoint, { method: 'DELETE' })
}