import axios, { AxiosError } from 'axios';
import type { ErrorResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Send cookies
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for 401 handling
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ErrorResponse>) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      // Session expired - redirect to login (but not if already on login page)
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
