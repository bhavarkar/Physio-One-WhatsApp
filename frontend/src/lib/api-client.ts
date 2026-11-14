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

export interface RegisteredTool {
  name: string;
  description: string;
  parameters_schema: Record<string, any>;
  requires_permission: string;
  is_mutation: boolean;
  is_idempotent: boolean;
  timeout_seconds: number;
  is_enabled: boolean;
}

export interface AIModel {
  id: string;
  provider_id: string;
  provider_name: string;
  model_identifier: string;
  display_name: string;
  supports_tools: boolean;
  supports_vision: boolean;
  max_context_tokens: number;
  created_at: string;
}

export interface AIProvider {
  id: string;
  name: string;
  base_url: string;
  has_api_key: boolean;
  masked_api_key: string;
  is_enabled: boolean;
  config?: Record<string, any> | null;
  health_status: string;
  last_validated_at?: string | null;
  last_validation_result?: Record<string, any> | null;
  models: AIModel[];
  created_at: string;
  updated_at: string;
}

export interface AIProviderTestResult {
  is_valid: boolean;
  status: string;
  latency_ms: number;
  error_message?: string | null;
  detected_models: string[];
  capabilities: Record<string, boolean>;
  details?: Record<string, any> | null;
}

export interface AIAgent {
  id: string;
  name: string;
  description: string | null;
  primary_model_id: string;
  primary_model_identifier: string;
  primary_provider_name: string;
  fallback_model_id: string | null;
  fallback_model_identifier: string | null;
  fallback_provider_name: string | null;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  supported_languages: string[];
  allowed_tools: string[];
  max_execution_steps: number;
  execution_timeout_seconds: number;
  context_budget_tokens: number;
  knowledge_base_id?: string | null;
  rag_enabled?: boolean;
  rag_similarity_threshold?: number;
  rag_top_k?: number;
  current_version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AIAgentVersion {
  id: string;
  agent_id: string;
  version_number: number;
  system_prompt: string;
  temperature: number;
  max_tokens?: number | null;
  model_identifier?: string | null;
  allowed_tools?: string[] | null;
  max_execution_steps?: number | null;
  changed_by_user_id?: string | null;
  change_summary?: string | null;
  created_at: string;
}

export interface AIAgentTestResponse {
  session_id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  response_text: string;
  steps: Array<{
    step: number;
    duration_ms: number;
    tool_calls_count: number;
    has_content: boolean;
  }>;
  tool_calls: Array<{
    step: number;
    id: string;
    name: string;
    arguments: Record<string, any>;
    result: Record<string, any>;
  }>;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  duration_ms: number;
  model: string;
  provider: string;
  error_message?: string | null;
}

export interface AgentExecutionStep {
  step_number: number;
  status: string;
  response_text?: string | null;
  tool_calls?: Array<any> | null;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
  error_message?: string | null;
  created_at: string;
}

export interface AgentExecutionSession {
  id: string;
  agent_id: string;
  agent_version_id?: string | null;
  conversation_id?: string | null;
  status: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_execution_steps: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  created_at: string;
  executions: AgentExecutionStep[];
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  embedding_model: string;
  vector_dimension: number;
  is_active: boolean;
  created_by_id: string | null;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledge_base_id: string;
  title: string;
  filename: string;
  file_type: string;
  file_url: string;
  file_size_bytes: number;
  source_hash: string | null;
  chunk_count: number;
  version: number;
  status: 'pending' | 'processing' | 'ready' | 'failed' | 'archived';
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  chunk_text: string;
  chunk_metadata: Record<string, any> | null;
  created_at: string;
}

export interface KnowledgeSearchSnippet {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_version: number;
  knowledge_base_id: string;
  knowledge_base_name: string;
  chunk_index: number;
  chunk_text: string;
  similarity_score: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  count: number;
  retrieval_latency_ms: number;
  results: KnowledgeSearchSnippet[];
}

export interface ConversationMemory {
  id: string;
  contact_id: string;
  conversation_id: string | null;
  memory_type: string;
  content: string;
  confidence_score: number;
  is_active: boolean;
  source_message_id: string | null;
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

  // --- LLM Providers & Models ---
  getLLMProviders: () => apiFetch<AIProvider[]>('/api/v1/llm/providers'),

  createLLMProvider: (data: { name: string; base_url: string; api_key: string; is_enabled?: boolean; config?: Record<string, any> }) =>
    apiFetch<AIProvider>('/api/v1/llm/providers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateLLMProvider: (providerId: string, data: { base_url?: string; api_key?: string; is_enabled?: boolean; config?: Record<string, any> }) =>
    apiFetch<AIProvider>(`/api/v1/llm/providers/${providerId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  testLLMProvider: (providerId: string) =>
    apiFetch<AIProviderTestResult>(`/api/v1/llm/providers/${providerId}/test`, {
      method: 'POST',
    }),

  getLLMModels: () => apiFetch<AIModel[]>('/api/v1/llm/models'),

  // --- AI Agents & Versioning ---
  getAgents: () => apiFetch<AIAgent[]>('/api/v1/agents'),

  getAgent: (agentId: string) => apiFetch<AIAgent>(`/api/v1/agents/${agentId}`),

  createAgent: (data: {
    name: string;
    description?: string;
    primary_model_id: string;
    fallback_model_id?: string;
    system_prompt: string;
    temperature?: number;
    max_tokens?: number;
    allowed_tools?: string[];
    max_execution_steps?: number;
    execution_timeout_seconds?: number;
    context_budget_tokens?: number;
    knowledge_base_id?: string | null;
    rag_enabled?: boolean;
    rag_similarity_threshold?: number;
    rag_top_k?: number;
    is_active?: boolean;
  }) =>
    apiFetch<AIAgent>('/api/v1/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAgent: (
    agentId: string,
    data: {
      name?: string;
      description?: string;
      primary_model_id?: string;
      fallback_model_id?: string;
      system_prompt?: string;
      temperature?: number;
      max_tokens?: number;
      allowed_tools?: string[];
      max_execution_steps?: number;
      execution_timeout_seconds?: number;
      context_budget_tokens?: number;
      knowledge_base_id?: string | null;
      rag_enabled?: boolean;
      rag_similarity_threshold?: number;
      rag_top_k?: number;
      is_active?: boolean;
      change_summary?: string;
    }
  ) =>
    apiFetch<AIAgent>(`/api/v1/agents/${agentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getAgentVersions: (agentId: string) =>
    apiFetch<AIAgentVersion[]>(`/api/v1/agents/${agentId}/versions`),

  testAgent: (agentId: string, data: { message: string; allow_fallback?: boolean }) =>
    apiFetch<AIAgentTestResponse>(`/api/v1/agents/${agentId}/test`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getAgentExecutions: (agentId: string, limit = 20, offset = 0) =>
    apiFetch<AgentExecutionSession[]>(`/api/v1/agents/${agentId}/executions?limit=${limit}&offset=${offset}`),

  getExecutionSessionDetail: (executionId: string) =>
    apiFetch<AgentExecutionSession>(`/api/v1/agents/executions/${executionId}`),

  getTools: () => apiFetch<RegisteredTool[]>('/api/v1/tools'),

  // --- Knowledge Bases & RAG ---
  getKnowledgeBases: (activeOnly = false) =>
    apiFetch<KnowledgeBase[]>(`/api/v1/knowledge/bases?active_only=${activeOnly}`),

  getKnowledgeBase: (kbId: string) =>
    apiFetch<KnowledgeBase>(`/api/v1/knowledge/bases/${kbId}`),

  createKnowledgeBase: (data: {
    name: string;
    description?: string;
    embedding_model?: string;
    vector_dimension?: number;
  }) =>
    apiFetch<KnowledgeBase>('/api/v1/knowledge/bases', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateKnowledgeBase: (
    kbId: string,
    data: { name?: string; description?: string; is_active?: boolean }
  ) =>
    apiFetch<KnowledgeBase>(`/api/v1/knowledge/bases/${kbId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteKnowledgeBase: (kbId: string) =>
    apiFetch<void>(`/api/v1/knowledge/bases/${kbId}`, {
      method: 'DELETE',
    }),

  getKnowledgeDocuments: (kbId: string) =>
    apiFetch<KnowledgeDocument[]>(`/api/v1/knowledge/bases/${kbId}/documents`),

  getDocument: (docId: string) =>
    apiFetch<KnowledgeDocument>(`/api/v1/knowledge/documents/${docId}`),

  uploadKnowledgeDocument: (formData: FormData) =>
    apiFetch<KnowledgeDocument>('/api/v1/knowledge/documents/upload', {
      method: 'POST',
      body: formData,
    }),

  reprocessDocument: (docId: string) =>
    apiFetch<KnowledgeDocument>(`/api/v1/knowledge/documents/${docId}/reprocess`, {
      method: 'POST',
    }),

  archiveDocument: (docId: string) =>
    apiFetch<KnowledgeDocument>(`/api/v1/knowledge/documents/${docId}/archive`, {
      method: 'POST',
    }),

  deleteKnowledgeDocument: (docId: string) =>
    apiFetch<void>(`/api/v1/knowledge/documents/${docId}`, {
      method: 'DELETE',
    }),

  searchKnowledge: (data: {
    query: string;
    knowledge_base_id?: string;
    top_k?: number;
    similarity_threshold?: number;
  }) =>
    apiFetch<KnowledgeSearchResponse>('/api/v1/knowledge/search', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  testKnowledgeRetrieval: (data: {
    query: string;
    knowledge_base_id?: string;
    top_k?: number;
    similarity_threshold?: number;
  }) =>
    apiFetch<KnowledgeSearchResponse>('/api/v1/knowledge/test-retrieval', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getContactMemories: (contactId: string) =>
    apiFetch<ConversationMemory[]>(`/api/v1/knowledge/contacts/${contactId}/memories`),

  createContactMemory: (
    contactId: string,
    data: { content: string; memory_type?: string; confidence_score?: number }
  ) =>
    apiFetch<ConversationMemory>(`/api/v1/knowledge/contacts/${contactId}/memories`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteContactMemory: (memoryId: string, contactId: string) =>
    apiFetch<void>(`/api/v1/knowledge/contacts/${contactId}/memories/${memoryId}`, {
      method: 'DELETE',
    }),
};

export const apiClient = api;

