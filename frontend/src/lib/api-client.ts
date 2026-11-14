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

export interface AutomationRule {
  id: string;
  name: string;
  trigger_type: string;
  condition_json: Record<string, unknown>;
  action_type: string;
  is_enabled: boolean;
  automation_type: string;
  trigger_event: string;
  delay_minutes: number;
  business_hours_only: boolean;
  start_hour: string;
  end_hour: string;
  permitted_days: number[];
  timezone: string;
  template_id?: string | null;
  template_name?: string | null;
  fallback_body?: string | null;
  provider: string;
  max_sends_per_contact: number;
  cooldown_hours: number;
  retry_policy: Record<string, unknown>;
  eligibility_filters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AutomationScheduledJob {
  id: string;
  rule_id?: string | null;
  rule_name?: string | null;
  automation_type: string;
  contact_id: string;
  contact_phone?: string | null;
  contact_name?: string | null;
  conversation_id?: string | null;
  appointment_id?: string | null;
  patient_id?: string | null;
  scheduled_for: string;
  status: string;
  suppression_reason?: string | null;
  suppression_details?: Record<string, unknown> | null;
  payload: Record<string, unknown>;
  rendered_message?: string | null;
  template_id?: string | null;
  template_name?: string | null;
  provider: string;
  provider_message_id?: string | null;
  attempt_count: number;
  max_attempts: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  idempotency_key: string;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationMessageTemplate {
  id: string;
  name: string;
  provider: string;
  language: string;
  category: string;
  approval_status: string;
  body: string;
  variables: string[];
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutomationExecutionLog {
  id: string;
  job_id: string;
  rule_id?: string | null;
  contact_id: string;
  automation_type: string;
  action: string;
  status_before?: string | null;
  status_after?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AutomationSuppressionLog {
  id: string;
  job_id?: string | null;
  rule_id?: string | null;
  contact_id: string;
  reason: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AutomationSettings {
  id: string;
  outbound_enabled: boolean;
  default_timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  business_hours_start: string;
  business_hours_end: string;
  worker_scan_interval_seconds: number;
  max_retries: number;
  default_cooldown_hours: number;
  rate_limit_per_minute: number;
  emergency_stop: boolean;
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

export interface AutomationRule {
  id: string;
  name: string;
  trigger_type: string;
  condition_json: Record<string, unknown>;
  action_type: string;
  is_enabled: boolean;
  automation_type: string;
  trigger_event: string;
  delay_minutes: number;
  business_hours_only: boolean;
  start_hour: string;
  end_hour: string;
  permitted_days: number[];
  timezone: string;
  template_id?: string | null;
  template_name?: string | null;
  fallback_body?: string | null;
  provider: string;
  max_sends_per_contact: number;
  cooldown_hours: number;
  retry_policy: Record<string, unknown>;
  eligibility_filters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AutomationScheduledJob {
  id: string;
  rule_id?: string | null;
  rule_name?: string | null;
  automation_type: string;
  contact_id: string;
  contact_phone?: string | null;
  contact_name?: string | null;
  conversation_id?: string | null;
  appointment_id?: string | null;
  patient_id?: string | null;
  scheduled_for: string;
  status: string;
  suppression_reason?: string | null;
  suppression_details?: Record<string, unknown> | null;
  payload: Record<string, unknown>;
  rendered_message?: string | null;
  template_id?: string | null;
  template_name?: string | null;
  provider: string;
  provider_message_id?: string | null;
  attempt_count: number;
  max_attempts: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  idempotency_key: string;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationMessageTemplate {
  id: string;
  name: string;
  provider: string;
  language: string;
  category: string;
  approval_status: string;
  body: string;
  variables: string[];
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutomationExecutionLog {
  id: string;
  job_id: string;
  rule_id?: string | null;
  contact_id: string;
  automation_type: string;
  action: string;
  status_before?: string | null;
  status_after?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AutomationSuppressionLog {
  id: string;
  job_id?: string | null;
  rule_id?: string | null;
  contact_id: string;
  reason: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AutomationSettings {
  id: string;
  outbound_enabled: boolean;
  default_timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  business_hours_start: string;
  business_hours_end: string;
  worker_scan_interval_seconds: number;
  max_retries: number;
  default_cooldown_hours: number;
  rate_limit_per_minute: number;
  emergency_stop: boolean;
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

export interface AppointmentWorkflowEvent {
  id: string;
  workflow_id: string;
  from_status: string | null;
  to_status: string | null;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
  payload: Record<string, any>;
  notes: string | null;
  created_at: string;
}

export interface AppointmentConfirmation {
  id: string;
  workflow_id: string;
  confirmation_token: string;
  summary_text: string;
  slot_start: string;
  slot_end: string;
  is_confirmed: boolean;
  confirmed_at: string | null;
  expires_at: string;
  created_at: string;
}

export interface AppointmentApprovalRequest {
  id: string;
  workflow_id: string;
  workflow_version: number;
  operation: string;
  status: string;
  proposal_summary: Record<string, any>;
  staff_id: string | null;
  decision_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface AppointmentWorkflow {
  id: string;
  conversation_id: string;
  contact_id: string;
  patient_id: string | null;
  patient_name: string | null;
  patient_phone: string | null;
  appointment_id: string | null;
  intent: string;
  status: string;
  workflow_version: number;
  selected_slot_start: string | null;
  selected_slot_end: string | null;
  practitioner_name: string;
  service_type: string;
  duration_minutes: number;
  collected_data: Record<string, any>;
  proposed_changes: Record<string, any>;
  confirmation_status: string;
  confirmation_token: string | null;
  confirmation_requested_at: string | null;
  confirmed_at: string | null;
  approval_status: string;
  approved_by_id: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  clarification_notes: string | null;
  expires_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  events?: AppointmentWorkflowEvent[];
  confirmations?: AppointmentConfirmation[];
  approval_requests?: AppointmentApprovalRequest[];
}

export interface AppointmentWorkflowListResponse {
  items: AppointmentWorkflow[];
  total: number;
  page: number;
  page_size: number;
}

export interface AppointmentWorkflowSettings {
  id: string;
  policy_mode: string;
  require_patient_confirmation: boolean;
  workflow_expiry_minutes: number;
  confirmation_expiry_minutes: number;
  max_reschedule_count: number;
  allow_cancellation_within_hours: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutomationRule {
  id: string;
  name: string;
  trigger_type: string;
  condition_json: Record<string, unknown>;
  action_type: string;
  is_enabled: boolean;
  automation_type: string;
  trigger_event: string;
  delay_minutes: number;
  business_hours_only: boolean;
  start_hour: string;
  end_hour: string;
  permitted_days: number[];
  timezone: string;
  template_id?: string | null;
  template_name?: string | null;
  fallback_body?: string | null;
  provider: string;
  max_sends_per_contact: number;
  cooldown_hours: number;
  retry_policy: Record<string, unknown>;
  eligibility_filters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AutomationScheduledJob {
  id: string;
  rule_id?: string | null;
  rule_name?: string | null;
  automation_type: string;
  contact_id: string;
  contact_phone?: string | null;
  contact_name?: string | null;
  conversation_id?: string | null;
  appointment_id?: string | null;
  patient_id?: string | null;
  scheduled_for: string;
  status: string;
  suppression_reason?: string | null;
  suppression_details?: Record<string, unknown> | null;
  payload: Record<string, unknown>;
  rendered_message?: string | null;
  template_id?: string | null;
  template_name?: string | null;
  provider: string;
  provider_message_id?: string | null;
  attempt_count: number;
  max_attempts: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  idempotency_key: string;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AutomationMessageTemplate {
  id: string;
  name: string;
  provider: string;
  language: string;
  category: string;
  approval_status: string;
  body: string;
  variables: string[];
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutomationExecutionLog {
  id: string;
  job_id: string;
  rule_id?: string | null;
  contact_id: string;
  automation_type: string;
  action: string;
  status_before?: string | null;
  status_after?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AutomationSuppressionLog {
  id: string;
  job_id?: string | null;
  rule_id?: string | null;
  contact_id: string;
  reason: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AutomationSettings {
  id: string;
  outbound_enabled: boolean;
  default_timezone: string;
  quiet_hours_start: string;
  quiet_hours_end: string;
  business_hours_start: string;
  business_hours_end: string;
  worker_scan_interval_seconds: number;
  max_retries: number;
  default_cooldown_hours: number;
  rate_limit_per_minute: number;
  emergency_stop: boolean;
  created_at: string;
  updated_at: string;
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

export interface ConversationMessage {
  id: string;
  provider: string;
  direction: 'inbound' | 'outbound';
  message_type: string;
  body: string | null;
  media_url: string | null;
  media_mime_type: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface AIResponseDraft {
  id: string;
  conversation_id: string;
  session_id: string | null;
  agent_id: string | null;
  inbound_job_id: string | null;
  aggregated_inbound_text: string;
  draft_text: string;
  ai_mode: string;
  dispatched: boolean;
  outbound_message_id: string | null;
  created_at: string;
}

export interface ConversationHandoff {
  id: string;
  conversation_id: string;
  action: string;
  from_state: string | null;
  to_state: string | null;
  reason: string | null;
  actor_type: string;
  actor_id: string | null;
  created_at: string;
}

export interface ConversationListItem {
  id: string;
  contact_id: string;
  contact_name: string | null;
  contact_phone: string;
  status: string;
  is_human_takeover: boolean;
  ai_paused: boolean;
  opted_out: boolean;
  last_message_at: string | null;
  last_message_body: string | null;
  last_message_direction: string | null;
  unread_count: number;
  pending_draft_count: number;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  contact_id: string;
  contact_name: string | null;
  contact_phone: string;
  status: string;
  is_human_takeover: boolean;
  ai_paused: boolean;
  opted_out: boolean;
  created_at: string;
  updated_at: string | null;
  messages: ConversationMessage[];
  drafts: AIResponseDraft[];
  handoffs: ConversationHandoff[];
}

export interface AIInboundSettings {
  id: string;
  account_id: string | null;
  ai_mode: 'disabled' | 'shadow' | 'live';
  active_agent_id: string | null;
  active_agent_name: string | null;
  debounce_seconds: number;
  max_ai_steps: number;
  processing_timeout_seconds: number;
  opt_out_keywords: string[];
  emergency_keywords: string[];
  is_active: boolean;
  updated_at: string | null;
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

  // --- Appointment AI Workflows & Approvals (Task 10) ---
  getAppointmentWorkflows: (params?: {
    status?: string;
    intent?: string;
    conversation_id?: string;
    patient_id?: string;
    page?: number;
    page_size?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.intent) searchParams.set('intent', params.intent);
    if (params?.conversation_id) searchParams.set('conversation_id', params.conversation_id);
    if (params?.patient_id) searchParams.set('patient_id', params.patient_id);
    if (params?.page) searchParams.set('page', params.page.toString());
    if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
    const qs = searchParams.toString();
    return apiFetch<AppointmentWorkflowListResponse>(`/api/v1/appointment-workflows${qs ? `?${qs}` : ''}`);
  },

  getPendingApprovals: () =>
    apiFetch<AppointmentWorkflow[]>('/api/v1/appointment-workflows/approvals'),

  getAppointmentWorkflowDetails: (workflowId: string) =>
    apiFetch<AppointmentWorkflow>(`/api/v1/appointment-workflows/${workflowId}`),

  getAppointmentWorkflowHistory: (workflowId: string) =>
    apiFetch<AppointmentWorkflowEvent[]>(`/api/v1/appointment-workflows/${workflowId}/history`),

  approveAppointmentWorkflow: (workflowId: string, data?: { notes?: string }) =>
    apiFetch<{ success: boolean; result: any }>(`/api/v1/appointment-workflows/${workflowId}/approve`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  rejectAppointmentWorkflow: (workflowId: string, data: { reason: string; notes?: string }) =>
    apiFetch<{ success: boolean; result: any }>(`/api/v1/appointment-workflows/${workflowId}/reject`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  requestWorkflowClarification: (workflowId: string, data: { notes: string }) =>
    apiFetch<{ success: boolean; result: any }>(`/api/v1/appointment-workflows/${workflowId}/request-clarification`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getAppointmentWorkflowSettings: () =>
    apiFetch<AppointmentWorkflowSettings>('/api/v1/appointment-workflows/settings'),

  updateAppointmentWorkflowSettings: (data: Partial<AppointmentWorkflowSettings>) =>
    apiFetch<AppointmentWorkflowSettings>('/api/v1/appointment-workflows/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
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

  // Inbound Conversations & Live Inbox
  getConversations: (params?: { status?: string; takeover_only?: boolean; search?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.takeover_only) searchParams.set('takeover_only', 'true');
    if (params?.search) searchParams.set('search', params.search);
    const qs = searchParams.toString();
    return apiFetch<ConversationListItem[]>(`/api/v1/conversations${qs ? `?${qs}` : ''}`);
  },

  getConversationDetail: (conversationId: string) =>
    apiFetch<ConversationDetail>(`/api/v1/conversations/${conversationId}`),

  sendConversationReply: (conversationId: string, data: { message: string; takeover?: boolean }) =>
    apiFetch<ConversationMessage>(`/api/v1/conversations/${conversationId}/reply`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  takeoverConversation: (conversationId: string, reason?: string) =>
    apiFetch<{ status: string; is_human_takeover: boolean; message: string }>(
      `/api/v1/conversations/${conversationId}/takeover`,
      {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }
    ),

  pauseAiConversation: (conversationId: string, reason?: string) =>
    apiFetch<{ status: string; ai_paused: boolean; message: string }>(
      `/api/v1/conversations/${conversationId}/pause-ai`,
      {
        method: 'POST',
        body: JSON.stringify({ reason }),
      }
    ),

  resumeAiConversation: (conversationId: string) =>
    apiFetch<{ status: string; is_human_takeover: boolean; ai_paused: boolean; message: string }>(
      `/api/v1/conversations/${conversationId}/resume-ai`,
      {
        method: 'POST',
      }
    ),

  getAiInboundSettings: () => apiFetch<AIInboundSettings>('/api/v1/ai-inbound/settings'),

  updateAiInboundSettings: (data: {
    ai_mode?: string;
    active_agent_id?: string;
    debounce_seconds?: number;
    max_ai_steps?: number;
    processing_timeout_seconds?: number;
    opt_out_keywords?: string[];
    emergency_keywords?: string[];
    is_active?: boolean;
  }) =>
    apiFetch<AIInboundSettings>('/api/v1/ai-inbound/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  processDueInboundJobs: (limit?: number) =>
    apiFetch<{ processed_count: number; jobs: Array<{ job_id: string; outcome: Record<string, unknown> }> }>(
      `/api/v1/ai-inbound/process-due${limit ? `?limit=${limit}` : ''}`,
      {
        method: 'POST',
      }
    ),

  // ---------------------------------------------------------------------------
  // Scheduled Automations (Task 11)
  // ---------------------------------------------------------------------------
  getAutomationSettings: () => apiFetch<AutomationSettings>('/api/v1/automations/settings'),

  updateAutomationSettings: (data: Partial<AutomationSettings>) =>
    apiFetch<AutomationSettings>('/api/v1/automations/settings', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getAutomationRules: (params?: { automation_type?: string; is_enabled?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.automation_type) q.set('automation_type', params.automation_type);
    if (params?.is_enabled !== undefined) q.set('is_enabled', String(params.is_enabled));
    const qs = q.toString();
    return apiFetch<{ items: AutomationRule[]; total: number }>(`/api/v1/automations/rules${qs ? `?${qs}` : ''}`);
  },

  createAutomationRule: (data: Partial<AutomationRule>) =>
    apiFetch<AutomationRule>('/api/v1/automations/rules', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAutomationRule: (id: string, data: Partial<AutomationRule>) =>
    apiFetch<AutomationRule>(`/api/v1/automations/rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  enableAutomationRule: (id: string) =>
    apiFetch<AutomationRule>(`/api/v1/automations/rules/${id}/enable`, {
      method: 'POST',
    }),

  disableAutomationRule: (id: string) =>
    apiFetch<AutomationRule>(`/api/v1/automations/rules/${id}/disable`, {
      method: 'POST',
    }),

  getScheduledJobs: (params?: { status?: string; automation_type?: string; contact_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.automation_type) q.set('automation_type', params.automation_type);
    if (params?.contact_id) q.set('contact_id', params.contact_id);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiFetch<{ items: AutomationScheduledJob[]; total: number }>(`/api/v1/automations/jobs${qs ? `?${qs}` : ''}`);
  },

  createStaffScheduledJob: (data: {
    contact_id: string;
    scheduled_for: string;
    reason: string;
    message_text?: string;
    template_id?: string;
    conversation_id?: string;
    appointment_id?: string;
    provider?: string;
  }) =>
    apiFetch<AutomationScheduledJob>('/api/v1/automations/jobs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  cancelScheduledJob: (id: string, reason?: string) =>
    apiFetch<AutomationScheduledJob>(`/api/v1/automations/jobs/${id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'Cancelled by staff' }),
    }),

  retryScheduledJob: (id: string, reset_attempts: boolean = true) =>
    apiFetch<AutomationScheduledJob>(`/api/v1/automations/jobs/${id}/retry`, {
      method: 'POST',
      body: JSON.stringify({ reset_attempts }),
    }),

  getAutomationTemplates: () =>
    apiFetch<{ items: AutomationMessageTemplate[]; total: number }>('/api/v1/automations/templates'),

  createAutomationTemplate: (data: Partial<AutomationMessageTemplate>) =>
    apiFetch<AutomationMessageTemplate>('/api/v1/automations/templates', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAutomationTemplate: (id: string, data: Partial<AutomationMessageTemplate>) =>
    apiFetch<AutomationMessageTemplate>(`/api/v1/automations/templates/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getAutomationExecutions: (params?: { job_id?: string; contact_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.job_id) q.set('job_id', params.job_id);
    if (params?.contact_id) q.set('contact_id', params.contact_id);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiFetch<{ items: AutomationExecutionLog[]; total: number }>(`/api/v1/automations/executions${qs ? `?${qs}` : ''}`);
  },

  getAutomationSuppressions: (params?: { contact_id?: string; reason?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.contact_id) q.set('contact_id', params.contact_id);
    if (params?.reason) q.set('reason', params.reason);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiFetch<{ items: AutomationSuppressionLog[]; total: number }>(`/api/v1/automations/suppressions${qs ? `?${qs}` : ''}`);
  },

  testAutomationPreview: (data: {
    rule_id?: string;
    template_id?: string;
    inline_body?: string;
    contact_id: string;
    appointment_id?: string;
    mock_variables?: Record<string, string>;
  }) =>
    apiFetch<{
      rendered_message: string;
      eligible: boolean;
      suppression_reasons: string[];
      service_window_open: boolean;
      requires_approved_template: boolean;
      in_business_hours: boolean;
      in_quiet_hours: boolean;
      next_eligible_send_time?: string | null;
    }>('/api/v1/automations/test', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  triggerAutomationWorker: (limit: number = 20) =>
    apiFetch<{
      scanned_count: number;
      locked_count: number;
      sent_count: number;
      suppressed_count: number;
      failed_count: number;
      server_time: string;
    }>(`/api/v1/automations/process-due?limit=${limit}`, { method: 'POST' }),

  triggerInactivityScan: () =>
    apiFetch<{ newly_scheduled_count: number }>('/api/v1/automations/scan-inactivity', { method: 'POST' }),

  // Campaign & Instagram Re-engagement (Task 12)
  getCampaignMedia: () => apiFetch<{ items: CampaignMedia[]; total: number }>('/api/v1/campaign-media'),
  createCampaignMedia: (data: {
    title: string;
    media_type: string;
    instagram_url?: string;
    storage_path?: string;
    caption?: string;
    tags?: string[];
  }) =>
    apiFetch<CampaignMedia>('/api/v1/campaign-media', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCampaignMedia: (id: string, data: Partial<CampaignMedia>) =>
    apiFetch<CampaignMedia>(`/api/v1/campaign-media/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteCampaignMedia: (id: string) =>
    apiFetch<{ message: string }>(`/api/v1/campaign-media/${id}`, { method: 'DELETE' }),

  getCampaigns: (params?: { campaign_type?: string; status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.campaign_type) q.set('campaign_type', params.campaign_type);
    if (params?.status) q.set('status', params.status);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiFetch<{ items: Campaign[]; total: number }>(`/api/v1/campaigns${qs ? `?${qs}` : ''}`);
  },
  getCampaign: (id: string) => apiFetch<Campaign>(`/api/v1/campaigns/${id}`),
  createCampaign: (data: Record<string, unknown>) =>
    apiFetch<Campaign>('/api/v1/campaigns', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCampaign: (id: string, data: Record<string, unknown>) =>
    apiFetch<Campaign>(`/api/v1/campaigns/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  previewCampaignAudience: (id: string, persist_recipients: boolean = false) =>
    apiFetch<CampaignAudiencePreview>(`/api/v1/campaigns/${id}/preview?persist_recipients=${persist_recipients}`, {
      method: 'POST',
    }),
  approveCampaign: (id: string, decision: 'approve' | 'reject', review_notes?: string) =>
    apiFetch<Campaign>(`/api/v1/campaigns/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ decision, review_notes }),
    }),
  scheduleCampaign: (id: string, scheduled_for?: string) =>
    apiFetch<Campaign>(`/api/v1/campaigns/${id}/schedule`, {
      method: 'POST',
      body: JSON.stringify({ scheduled_for }),
    }),
  pauseCampaign: (id: string) =>
    apiFetch<Campaign>(`/api/v1/campaigns/${id}/pause`, { method: 'POST' }),
  resumeCampaign: (id: string) =>
    apiFetch<Campaign>(`/api/v1/campaigns/${id}/resume`, { method: 'POST' }),
  cancelCampaign: (id: string) =>
    apiFetch<Campaign>(`/api/v1/campaigns/${id}/cancel`, { method: 'POST' }),
  getCampaignRecipients: (id: string, params?: { status?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set('status', params.status);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiFetch<{ items: CampaignRecipient[]; total: number }>(`/api/v1/campaigns/${id}/recipients${qs ? `?${qs}` : ''}`);
  },
  getCampaignAnalytics: (id: string) => apiFetch<CampaignAnalytics>(`/api/v1/campaigns/${id}/analytics`),
  importCampaignCsv: (csv_text: string) =>
    apiFetch<CampaignImportReport>('/api/v1/campaigns/import-csv', {
      method: 'POST',
      body: JSON.stringify({ csv_text }),
    }),
  getLegacyMigrationStatus: () => apiFetch<LegacyMigrationStatus>('/api/v1/legacy-migration/status'),
  runLegacyDryRun: () => apiFetch<LegacyMigrationDryRun>('/api/v1/legacy-migration/dry-run', { method: 'POST' }),
  setLegacyCutoverState: (data: { cutover_state: string; notes?: string }) =>
    apiFetch<LegacyMigrationStatus>('/api/v1/legacy-migration/cutover', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  triggerReengagementCycle: (limit: number = 25) =>
    apiFetch<{ scanned_campaigns: number; dispatched_count: number; suppressed_count: number; failed_count: number }>(
      `/api/v1/campaigns/worker/trigger?limit=${limit}`,
      { method: 'POST' }
    ),
};

export interface CampaignMedia {
  id: string;
  title: string;
  media_type: string;
  instagram_url?: string | null;
  storage_path?: string | null;
  caption?: string | null;
  tags?: string[] | null;
  is_active: boolean;
  file_size?: number | null;
  mime_type?: string | null;
  created_by_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CampaignVersion {
  id: string;
  campaign_id: string;
  version_number: number;
  title: string;
  target_audience_rules: Record<string, unknown>;
  template_name?: string | null;
  custom_message_body?: string | null;
  media_id?: string | null;
  rate_limit_per_minute: number;
  rate_limit_per_hour: number;
  batch_size: number;
  cooldown_days: number;
  provider: string;
  execution_window_start: string;
  execution_window_end: string;
  created_by_id?: string | null;
  change_summary?: string | null;
  created_at: string;
}

export interface CampaignApproval {
  id: string;
  campaign_id: string;
  version_number: number;
  reviewed_by_id: string;
  decision: 'approved' | 'rejected' | 'invalidated';
  review_notes?: string | null;
  created_at: string;
}

export interface Campaign {
  id: string;
  title: string;
  description?: string | null;
  campaign_type: 'instagram_reengagement' | 'patient_education' | 'seasonal_broadcast' | 'custom_broadcast';
  status: 'draft' | 'audience_prepared' | 'preview_ready' | 'awaiting_approval' | 'approved' | 'scheduled' | 'running' | 'paused' | 'completed' | 'cancelled';
  provider: 'meta' | 'ycloud';
  is_approved: boolean;
  approved_by_id?: string | null;
  approved_at?: string | null;
  approved_version?: number | null;
  approval_notes?: string | null;
  template_name?: string | null;
  template_id?: string | null;
  custom_message_body?: string | null;
  media_id?: string | null;
  target_audience_rules: Record<string, unknown>;
  scheduled_for?: string | null;
  execution_window_start: string;
  execution_window_end: string;
  rate_limit_per_minute: number;
  rate_limit_per_hour: number;
  batch_size: number;
  cooldown_days: number;
  total_recipients: number;
  total_sent: number;
  total_delivered: number;
  total_read: number;
  total_converted: number;
  total_suppressed: number;
  total_failed: number;
  current_version: number;
  created_by_id?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  media?: CampaignMedia | null;
  approvals?: CampaignApproval[];
}

export interface CampaignRecipient {
  id: string;
  campaign_id: string;
  contact_id: string;
  phone_e164: string;
  contact_name?: string | null;
  status: 'queued' | 'sending' | 'sent' | 'delivered' | 'read' | 'failed' | 'suppressed' | 'converted';
  suppression_reason?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  read_at?: string | null;
  converted_at?: string | null;
  attempts: number;
  error_message?: string | null;
}

export interface CampaignAudiencePreview {
  campaign_id: string;
  total_evaluated: number;
  eligible_count: number;
  suppressed_count: number;
  suppression_breakdown: Record<string, number>;
  sample_eligible_recipients: Array<{
    contact_id: string;
    wa_id: string;
    name?: string | null;
    last_active_at?: string | null;
  }>;
  sample_rendered_message?: string | null;
}

export interface CampaignImportReport {
  total_rows: number;
  accepted_count: number;
  rejected_count: number;
  duplicate_count: number;
  created_contacts_count: number;
  rejections: Array<{ row: number; phone?: string; reason: string }>;
}

export interface CampaignAnalytics {
  campaign_id: string;
  title: string;
  campaign_type: string;
  status: string;
  total_recipients: number;
  total_sent: number;
  total_delivered: number;
  total_read: number;
  total_converted: number;
  total_suppressed: number;
  total_failed: number;
  delivery_rate_pct: number;
  read_rate_pct: number;
  conversion_rate_pct: number;
  failure_rate_pct: number;
  attribution_window_hours: number;
  suppression_breakdown: Record<string, number>;
}

export interface LegacyMigrationStatus {
  cutover_state: 'legacy_active' | 'shadow_comparison' | 'migration_ready' | 'new_active' | 'rolled_back';
  legacy_system_name: string;
  last_dry_run_at?: string | null;
  dry_run_discrepancy_count: number;
  is_live_dispatch_blocked: boolean;
  notes?: string | null;
}

export interface LegacyMigrationDryRun {
  total_evaluated: number;
  legacy_predicted_count: number;
  new_engine_eligible_count: number;
  discrepancy_count: number;
  suppression_summary: Record<string, number>;
  discrepancies: Array<{
    contact_id: string;
    wa_id: string;
    legacy_status: string;
    new_engine_status: string;
    reason: string;
  }>;
}

export const apiClient = api;

