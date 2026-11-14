import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AutomationsPage from './page';
import {
  api,
  AutomationRule,
  AutomationScheduledJob,
  AutomationMessageTemplate,
  AutomationSettings,
  AutomationExecutionLog,
  AutomationSuppressionLog,
} from '@/lib/api-client';

const mockSettings: AutomationSettings = {
  id: 'set-1',
  outbound_enabled: false,
  default_timezone: 'Asia/Kolkata',
  quiet_hours_start: '21:00',
  quiet_hours_end: '09:00',
  business_hours_start: '09:00',
  business_hours_end: '20:00',
  worker_scan_interval_seconds: 15,
  max_retries: 5,
  default_cooldown_hours: 24,
  rate_limit_per_minute: 60,
  emergency_stop: false,
  created_at: '2026-11-14T00:00:00Z',
  updated_at: '2026-11-14T00:00:00Z',
};

const mockRules: AutomationRule[] = [
  {
    id: 'rule-1',
    name: '24h Appointment Reminder',
    automation_type: 'appointment_reminder',
    trigger_type: 'appointment_scheduled',
    trigger_event: 'appointment_confirmed',
    condition_json: {},
    action_type: 'send_whatsapp_template',
    is_enabled: false,
    delay_minutes: 1440,
    business_hours_only: true,
    start_hour: '09:00',
    end_hour: '20:00',
    permitted_days: [1, 2, 3, 4, 5, 6],
    timezone: 'Asia/Kolkata',
    template_name: 'appointment_reminder_24h',
    fallback_body: 'Hello {{patient_name}}, reminder of your appointment at Physio One.',
    provider: 'meta',
    max_sends_per_contact: 1,
    cooldown_hours: 24,
    retry_policy: { max_attempts: 5 },
    eligibility_filters: {},
    created_at: '2026-11-14T00:00:00Z',
    updated_at: '2026-11-14T00:00:00Z',
  },
  {
    id: 'rule-2',
    name: 'Inactivity Follow-up (2h Stage 1)',
    automation_type: 'inactivity_followup',
    trigger_type: 'inactivity_detected',
    trigger_event: 'inactivity_detected',
    condition_json: {},
    action_type: 'send_whatsapp_template',
    is_enabled: false,
    delay_minutes: 120,
    business_hours_only: true,
    start_hour: '09:00',
    end_hour: '20:00',
    permitted_days: [1, 2, 3, 4, 5, 6],
    timezone: 'Asia/Kolkata',
    template_name: 'inactivity_followup_stage1',
    fallback_body: 'Hello {{patient_name}}, would you like help with your appointment inquiry?',
    provider: 'meta',
    max_sends_per_contact: 1,
    cooldown_hours: 24,
    retry_policy: { max_attempts: 5 },
    eligibility_filters: {},
    created_at: '2026-11-14T00:00:00Z',
    updated_at: '2026-11-14T00:00:00Z',
  },
];

const mockJobs: AutomationScheduledJob[] = [
  {
    id: 'job-1',
    rule_id: 'rule-1',
    rule_name: '24h Appointment Reminder',
    automation_type: 'appointment_reminder',
    contact_id: 'contact-1',
    contact_phone: '+919876543210',
    contact_name: 'Ananya Sharma',
    conversation_id: 'conv-1',
    appointment_id: 'appt-1',
    patient_id: 'p-1',
    scheduled_for: '2026-11-18T10:00:00Z',
    status: 'scheduled',
    suppression_reason: null,
    suppression_details: null,
    payload: { patient_name: 'Ananya Sharma' },
    rendered_message: 'Hello Ananya Sharma, reminder of your appointment at Physio One.',
    provider: 'meta',
    provider_message_id: null,
    attempt_count: 0,
    max_attempts: 5,
    last_attempt_at: null,
    next_retry_at: null,
    idempotency_key: 'test-idemp-1',
    completed_at: null,
    created_at: '2026-11-14T10:00:00Z',
    updated_at: '2026-11-14T10:00:00Z',
  },
];

const mockTemplates: AutomationMessageTemplate[] = [
  {
    id: 'tmpl-1',
    name: 'appointment_reminder_24h',
    provider: 'meta',
    language: 'en',
    category: 'UTILITY',
    approval_status: 'APPROVED',
    body: 'Hello {{patient_name}}, this is a reminder of your appointment at Physio One on {{appointment_date}} at {{appointment_time}}.',
    variables: ['patient_name', 'appointment_date', 'appointment_time'],
    version: 1,
    is_active: true,
    created_at: '2026-11-14T00:00:00Z',
    updated_at: '2026-11-14T00:00:00Z',
  },
];

const mockExecutions: AutomationExecutionLog[] = [
  {
    id: 'exec-1',
    job_id: 'job-1',
    contact_id: 'contact-1',
    automation_type: 'appointment_reminder',
    action: 'DISPATCH_COMPLETED',
    status_before: 'queued',
    status_after: 'sent',
    provider: 'meta',
    provider_message_id: 'wamid.123',
    details: { sent: true },
    created_at: '2026-11-14T10:05:00Z',
  },
];

const mockSuppressions: AutomationSuppressionLog[] = [
  {
    id: 'sup-1',
    job_id: 'job-1',
    contact_id: 'contact-1',
    reason: 'QUIET_HOURS',
    details: { current_hour: 22 },
    created_at: '2026-11-14T16:30:00Z',
  },
];

jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    user: { id: 'u-admin', email: 'admin@physioone.com', full_name: 'Clinic Admin', role: { name: 'Admin' } },
    role: 'Admin',
    hasRole: () => true,
    hasPermission: () => true,
  }),
}));

describe('AutomationsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(api, 'getAutomationSettings').mockResolvedValue(mockSettings);
    jest.spyOn(api, 'getAutomationRules').mockResolvedValue({ items: mockRules, total: 2 });
    jest.spyOn(api, 'getScheduledJobs').mockResolvedValue({ items: mockJobs, total: 1 });
    jest.spyOn(api, 'getAutomationTemplates').mockResolvedValue({ items: mockTemplates, total: 1 });
    jest.spyOn(api, 'getAutomationExecutions').mockResolvedValue({ items: mockExecutions, total: 1 });
    jest.spyOn(api, 'getAutomationSuppressions').mockResolvedValue({ items: mockSuppressions, total: 1 });
    jest.spyOn(api, 'enableAutomationRule').mockResolvedValue({ ...mockRules[0], is_enabled: true });
    jest.spyOn(api, 'disableAutomationRule').mockResolvedValue({ ...mockRules[0], is_enabled: false });
    jest.spyOn(api, 'cancelScheduledJob').mockResolvedValue({ ...mockJobs[0], status: 'cancelled' });
    jest.spyOn(api, 'updateAutomationSettings').mockResolvedValue({ ...mockSettings, outbound_enabled: true });
    jest.spyOn(api, 'triggerAutomationWorker').mockResolvedValue({
      scanned_count: 5,
      locked_count: 5,
      sent_count: 5,
      suppressed_count: 0,
      failed_count: 0,
      server_time: '2026-11-14T12:00:00Z',
    });
  });

  it('renders page header, kill-switch banner, and metric cards', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('24h Appointment Reminder')).toBeInTheDocument();
    });

    expect(screen.getByText('Automations & Scheduled Messaging')).toBeInTheDocument();
    expect(screen.getByText(/Automated Outbound Dispatch: DISABLED \(Kill Switch Engaged\)/i)).toBeInTheDocument();
    expect(screen.getByText('MUTED')).toBeInTheDocument();

    expect(screen.getByText('Active Rules')).toBeInTheDocument();
    expect(screen.getByText('Pending / Queued Jobs')).toBeInTheDocument();
    expect(screen.getByText('Suppressed (Safety Gate)')).toBeInTheDocument();
    expect(screen.getByText('Failed / Dead-letter')).toBeInTheDocument();
  });

  it('renders automation rules and allows enabling a rule', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('24h Appointment Reminder')).toBeInTheDocument();
      expect(screen.getByText('Inactivity Follow-up (2h Stage 1)')).toBeInTheDocument();
    });

    const enableButtons = screen.getAllByRole('button', { name: /enable/i });
    expect(enableButtons.length).toBeGreaterThan(0);

    fireEvent.click(enableButtons[0]);

    await waitFor(() => {
      expect(api.enableAutomationRule).toHaveBeenCalledWith('rule-1');
    });
  });

  it('switches to Scheduled Jobs tab and displays scheduled job', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('24h Appointment Reminder')).toBeInTheDocument();
    });

    const jobsTab = screen.getByRole('button', { name: /Scheduled Jobs \(1\)/i });
    fireEvent.click(jobsTab);

    await waitFor(() => {
      expect(screen.getByText('Ananya Sharma')).toBeInTheDocument();
      expect(screen.getByText('+919876543210')).toBeInTheDocument();
      expect(screen.getByText('scheduled')).toBeInTheDocument();
    });
  });

  it('allows cancelling a scheduled job', async () => {
    jest.spyOn(window, 'confirm').mockReturnValue(true);

    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('24h Appointment Reminder')).toBeInTheDocument();
    });

    const jobsTab = screen.getByRole('button', { name: /Scheduled Jobs \(1\)/i });
    fireEvent.click(jobsTab);

    await waitFor(() => {
      expect(screen.getByText('Ananya Sharma')).toBeInTheDocument();
    });

    const cancelButton = screen.getByTitle('Cancel Job');
    fireEvent.click(cancelButton);

    await waitFor(() => {
      expect(api.cancelScheduledJob).toHaveBeenCalledWith('job-1', 'Cancelled via Automations Dashboard');
    });
  });

  it('switches to Templates tab and displays WhatsApp HSM templates', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('24h Appointment Reminder')).toBeInTheDocument();
    });

    const tmplTab = screen.getByRole('button', { name: /WhatsApp Templates \(1\)/i });
    fireEvent.click(tmplTab);

    await waitFor(() => {
      expect(screen.getByText('appointment_reminder_24h')).toBeInTheDocument();
      expect(screen.getByText('APPROVED')).toBeInTheDocument();
      expect(screen.getByText('{{patient_name}}')).toBeInTheDocument();
    });
  });

  it('switches to Worker & Settings tab and runs manual worker cycle', async () => {
    render(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText('24h Appointment Reminder')).toBeInTheDocument();
    });

    const settingsTab = screen.getByRole('button', { name: /Worker & Settings/i });
    fireEvent.click(settingsTab);

    await waitFor(() => {
      expect(screen.getByText('Operating Timezone')).toBeInTheDocument();
      expect(screen.getAllByText('Asia/Kolkata').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('09:00 - 20:00 IST')).toBeInTheDocument();
      expect(screen.getAllByText('21:00 - 09:00 IST').length).toBeGreaterThanOrEqual(1);
    });

    const runWorkerButton = screen.getByRole('button', { name: /Run Automation Worker Cycle Now/i });
    fireEvent.click(runWorkerButton);

    await waitFor(() => {
      expect(api.triggerAutomationWorker).toHaveBeenCalledWith(20);
      expect(screen.getByText('Worker Run Diagnostics')).toBeInTheDocument();
      expect(screen.getByText('Sent Successfully:')).toBeInTheDocument();
    });
  });
});
