/**
 * Centralized API Client for FastAPI Backend.
 *
 * Attaches the current Supabase session JWT as Bearer token on requests.
 * Authoritatively handles HTTP 401, 403, 404, 422, and 500 error responses.
 */

import { supabase } from './supabase';

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000/api/v1'
).replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}/${endpoint.replace(/^\//, '')}`;

  // Obtain valid JWT access token from Supabase session
  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData.session?.access_token;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    let errorData = null;

    try {
      errorData = await response.json();
      if (errorData?.detail) {
        if (typeof errorData.detail === 'string') {
          errorDetail = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          errorDetail = errorData.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
        }
      } else if (errorData?.message) {
        errorDetail = errorData.message;
      }
    } catch {
      // Non-JSON error body (e.g. 502/504 gateway response)
      errorDetail = response.statusText || errorDetail;
    }

    if (response.status === 401) {
      // Optional: emit event or trigger session refresh
      console.warn('Unauthorized API request (401). Token may be expired.');
    }

    throw new ApiError(response.status, errorDetail, errorData);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string, headers?: Record<string, string>) =>
    request<T>(endpoint, { method: 'GET', headers }),

  post: <T>(endpoint: string, body?: any, headers?: Record<string, string>) =>
    request<T>(endpoint, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      headers,
    }),

  patch: <T>(endpoint: string, body?: any, headers?: Record<string, string>) =>
    request<T>(endpoint, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      headers,
    }),

  delete: <T>(endpoint: string, headers?: Record<string, string>) =>
    request<T>(endpoint, { method: 'DELETE', headers }),
};
