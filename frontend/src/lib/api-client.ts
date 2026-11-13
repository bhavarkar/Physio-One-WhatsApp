/**
 * Centralized Typed API Client for Physio One WhatsApp AI Platform.
 * Single Organization Edition.
 *
 * Enforces:
 * - Cookie-based credentials ('include')
 * - Double-submit CSRF protection via 'X-CSRF-Token' header on state-mutating methods
 * - Structured error parsing and session handling
 */

export interface Permission {
  id: string;
  codename: string;
  description: string | null;
  module: string;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permissions?: Permission[];
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role: Role;
  created_at: string;
  updated_at: string;
}

export interface SetupStatusResponse {
  is_initialized: boolean;
  owner_count: number;
}

export interface UserSession {
  id: string;
  user_id: string;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface UserListResponse {
  users: User[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiErrorDetail {
  code?: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: Record<string, unknown>;

  constructor(status: number, message: string, code?: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * Extract CSRF token from document.cookie
 */
function getCsrfTokenFromCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Base fetch client wrapper
 */
async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = endpoint.startsWith('http') ? endpoint : endpoint;

  const headers = new Headers(options.headers || {});
  
  if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  // State-mutating methods require CSRF token from cookie
  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCsrfTokenFromCookie();
    if (csrfToken && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRF-Token', csrfToken);
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Mandate HttpOnly cookies transmission
  });

  if (!response.ok) {
    let errorMessage = 'An unexpected error occurred.';
    let errorCode: string | undefined;
    let errorDetails: Record<string, unknown> | undefined;

    try {
      const data = await response.json();
      if (data?.error) {
        errorMessage = data.error.message || errorMessage;
        errorCode = data.error.code;
        errorDetails = data.error.details;
      } else if (data?.detail) {
        if (typeof data.detail === 'string') {
          errorMessage = data.detail;
        } else if (Array.isArray(data.detail)) {
          errorMessage = data.detail.map((e: { msg?: string }) => e.msg || 'Validation error').join(', ');
        }
      }
    } catch {
      errorMessage = response.statusText || errorMessage;
    }

    throw new ApiError(response.status, errorMessage, errorCode, errorDetails);
  }

  // Handle empty 204 or 200 responses
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return {} as T;
}

export const api = {
  // Authentication & System Setup
  getSetupStatus: () => apiFetch<SetupStatusResponse>('/api/v1/auth/setup-status'),
  
  setupInitialOwner: (data: { email: string; password: string; full_name: string }) =>
    apiFetch<User>('/api/v1/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  login: (data: { email: string; password: string }) =>
    apiFetch<User>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  logout: () =>
    apiFetch<{ message: string }>('/api/v1/auth/logout', {
      method: 'POST',
    }),

  getCurrentUser: () => apiFetch<User>('/api/v1/auth/me'),

  changePassword: (data: { current_password: string; new_password: string; revoke_other_sessions?: boolean }) =>
    apiFetch<{ message: string }>('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSessions: () => apiFetch<UserSession[]>('/api/v1/auth/sessions'),

  revokeSession: (sessionId: string) =>
    apiFetch<{ message: string }>(`/api/v1/auth/sessions/${sessionId}/revoke`, {
      method: 'POST',
    }),

  revokeAllOtherSessions: () =>
    apiFetch<{ message: string }>('/api/v1/auth/sessions/revoke-all', {
      method: 'POST',
    }),

  // User Management
  getRoles: () => apiFetch<Role[]>('/api/v1/users/roles'),

  getUsers: (params?: { page?: number; page_size?: number; search?: string; role_id?: string; is_active?: boolean }) => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
    if (params?.search) searchParams.set('search', params.search);
    if (params?.role_id) searchParams.set('role_id', params.role_id);
    if (params?.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    const qs = searchParams.toString();
    return apiFetch<UserListResponse>(`/api/v1/users${qs ? `?${qs}` : ''}`);
  },

  createUser: (data: { email: string; password: string; full_name: string; role_id: string }) =>
    apiFetch<User>('/api/v1/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getUserDetails: (userId: string) => apiFetch<User>(`/api/v1/users/${userId}`),

  updateUser: (userId: string, data: { email?: string; full_name?: string; role_id?: string; is_active?: boolean }) =>
    apiFetch<User>(`/api/v1/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deactivateUser: (userId: string) =>
    apiFetch<User>(`/api/v1/users/${userId}`, {
      method: 'DELETE',
    }),

  revokeUserSessions: (userId: string) =>
    apiFetch<{ message: string }>(`/api/v1/users/${userId}/revoke-sessions`, {
      method: 'POST',
    }),
};
