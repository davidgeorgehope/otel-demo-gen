// API configuration
const API_BASE_URL = process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:8000';

export { API_BASE_URL }; 