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

export interface WhatsAppConnection {
  id: string;
  provider: 'meta' | 'ycloud';
  account_name: string;
  phone_number_id: string;
  business_account_id: string | null;
  display_phone_number: string;
  webhook_verify_token: string;
  has_access_token: boolean;
  has_secret_key: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AppointmentHistory {
  id: string;
  appointment_id: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  from_start_time: string | null;
  from_end_time: string | null;
  to_start_time: string | null;
  to_end_time: string | null;
  reason: string | null;
  actor_type: string;
  actor_id: string | null;
  actor_name: string | null;
  notes: string | null;
  created_at: string;
}

export type AppointmentStatusType = 'scheduled' | 'confirmed' | 'completed' | 'cancelled' | 'no_show';

export interface Appointment {
  id: string;
  patient_id: string;
  patient_name: string | null;
  patient_phone: string | null;
  patient_email: string | null;
  practitioner_name: string;
  service_type: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  timezone: string;
  status: AppointmentStatusType;
  booked_by: string;
  external_appointment_id: string | null;
  rescheduled_from_id: string | null;
  created_by_id: string | null;
  updated_by_id: string | null;
  cancellation_reason: string | null;
  cancelled_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  history_entries?: AppointmentHistory[];
}

export interface AppointmentListResponse {
  appointments: Appointment[];
  total: number;
  page: number;
  page_size: number;
}

export interface TimeSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
  practitioner_name: string;
}

export interface AvailabilityResponse {
  date: string;
  is_open: boolean;
  operating_hours: { open: string; close: string };
  timezone: string;
  slots: TimeSlot[];
  message?: string | null;
}

export interface AppointmentCreateData {
  patient_id?: string;
  patient_name?: string;
  patient_phone?: string;
  patient_email?: string;
  start_time: string;
  duration_minutes?: number;
  practitioner_name?: string;
  service_type?: string;
  notes?: string;
  booked_by?: string;
}

export interface AppointmentRescheduleData {
  new_start_time: string;
  duration_minutes?: number;
  reason?: string;
  notes?: string;
}

export interface AppointmentCancelData {
  reason: string;
  notes?: string;
}

export interface ConnectionTestResult {
  is_valid: boolean;
  display_name: string | null;
  phone_number: string | null;
  error: string | null;
}

export interface TestMessageResult {
  success: boolean;
  message_id: string | null;
  provider_message_id: string | null;
  status: string;
  error: string | null;
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

  // WhatsApp Provider Connections
  getWhatsAppConnections: () =>
    apiFetch<WhatsAppConnection[]>('/api/v1/whatsapp/connections'),

  createWhatsAppConnection: (data: {
    provider: string;
    account_name: string;
    phone_number_id: string;
    display_phone_number: string;
    business_account_id?: string;
    webhook_verify_token: string;
    access_token: string;
    secret_key?: string;
    provider_config?: Record<string, unknown>;
    is_active?: boolean;
  }) =>
    apiFetch<WhatsAppConnection>('/api/v1/whatsapp/connections', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateWhatsAppConnection: (
    id: string,
    data: {
      account_name?: string;
      display_phone_number?: string;
      business_account_id?: string;
      webhook_verify_token?: string;
      access_token?: string;
      secret_key?: string;
      provider_config?: Record<string, unknown>;
      is_active?: boolean;
    }
  ) =>
    apiFetch<WhatsAppConnection>(`/api/v1/whatsapp/connections/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  testWhatsAppConnection: (id: string) =>
    apiFetch<ConnectionTestResult>(`/api/v1/whatsapp/connections/${id}/test`, {
      method: 'POST',
    }),

  sendWhatsAppTestMessage: (
    id: string,
    data: { recipient_phone: string; message_text: string }
  ) =>
    apiFetch<TestMessageResult>(`/api/v1/whatsapp/connections/${id}/send-test`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Clinical Appointments & Availability
  getAppointments: (params?: {
    date_from?: string;
    date_to?: string;
    status?: string;
    patient_id?: string;
    practitioner_name?: string;
    search?: string;
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: string;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.date_from) searchParams.set('date_from', params.date_from);
    if (params?.date_to) searchParams.set('date_to', params.date_to);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.patient_id) searchParams.set('patient_id', params.patient_id);
    if (params?.practitioner_name) searchParams.set('practitioner_name', params.practitioner_name);
    if (params?.search) searchParams.set('search', params.search);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
    if (params?.sort_by) searchParams.set('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.set('sort_order', params.sort_order);
    const qs = searchParams.toString();
    return apiFetch<AppointmentListResponse>(`/api/v1/appointments${qs ? `?${qs}` : ''}`);
  },

  getAppointmentDetails: (appointmentId: string) =>
    apiFetch<Appointment>(`/api/v1/appointments/${appointmentId}`),

  getAvailability: (date: string, durationMinutes: number = 45, practitionerName?: string) => {
    const searchParams = new URLSearchParams({ date, duration_minutes: durationMinutes.toString() });
    if (practitionerName) searchParams.set('practitioner_name', practitionerName);
    return apiFetch<AvailabilityResponse>(`/api/v1/appointments/availability?${searchParams.toString()}`);
  },

  createAppointment: (data: AppointmentCreateData) =>
    apiFetch<Appointment>('/api/v1/appointments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAppointment: (
    appointmentId: string,
    data: { practitioner_name?: string; service_type?: string; notes?: string }
  ) =>
    apiFetch<Appointment>(`/api/v1/appointments/${appointmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  rescheduleAppointment: (appointmentId: string, data: AppointmentRescheduleData) =>
    apiFetch<Appointment>(`/api/v1/appointments/${appointmentId}/reschedule`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  cancelAppointment: (appointmentId: string, data: AppointmentCancelData) =>
    apiFetch<Appointment>(`/api/v1/appointments/${appointmentId}/cancel`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  completeAppointment: (appointmentId: string, data?: { notes?: string }) =>
    apiFetch<Appointment>(`/api/v1/appointments/${appointmentId}/complete`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  markAppointmentNoShow: (appointmentId: string, data?: { notes?: string }) =>
    apiFetch<Appointment>(`/api/v1/appointments/${appointmentId}/no-show`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),
};

export const apiClient = api;

