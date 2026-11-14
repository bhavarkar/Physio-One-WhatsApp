import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AppointmentsPage from './page';
import { api, Appointment, AppointmentWorkflow } from '@/lib/api-client';

const mockAppointments: Appointment[] = [
  {
    id: 'appt-1',
    patient_id: 'p-1',
    patient_name: 'Ananya Sharma',
    patient_phone: '+919876543210',
    patient_email: 'ananya@example.com',
    practitioner_name: 'Dr. Physio One',
    service_type: 'Initial Physiotherapy Assessment',
    start_time: '2026-11-18T10:00:00Z',
    end_time: '2026-11-18T10:45:00Z',
    duration_minutes: 45,
    timezone: 'Asia/Kolkata',
    status: 'confirmed',
    booked_by: 'dashboard',
    external_appointment_id: null,
    rescheduled_from_id: null,
    created_by_id: null,
    updated_by_id: null,
    cancellation_reason: null,
    cancelled_at: null,
    notes: 'Referred for shoulder pain.',
    created_at: '2026-11-14T09:00:00Z',
    updated_at: '2026-11-14T09:00:00Z',
    history_entries: [
      {
        id: 'h-1',
        appointment_id: 'appt-1',
        action: 'created',
        from_status: null,
        to_status: 'confirmed',
        from_start_time: null,
        from_end_time: null,
        to_start_time: '2026-11-18T10:00:00Z',
        to_end_time: '2026-11-18T10:45:00Z',
        reason: null,
        actor_type: 'staff',
        actor_id: null,
        actor_name: 'Reception Desk',
        notes: 'Initial booking',
        created_at: '2026-11-14T09:00:00Z',
      },
    ],
  },
];

const mockWorkflows: AppointmentWorkflow[] = [
  {
    id: 'wf-1',
    conversation_id: 'conv-1',
    contact_id: 'contact-1',
    patient_id: 'p-1',
    patient_name: 'Rohan Mehra',
    patient_phone: '+919811223344',
    appointment_id: null,
    intent: 'book_appointment',
    status: 'awaiting_staff_approval',
    workflow_version: 2,
    selected_slot_start: '2026-11-19T11:30:00Z',
    selected_slot_end: '2026-11-19T12:15:00Z',
    practitioner_name: 'Dr. Physio One',
    service_type: 'Initial Physiotherapy Assessment',
    duration_minutes: 45,
    collected_data: { patient_name: 'Rohan Mehra' },
    proposed_changes: { formatted_display: 'Thursday, Nov 19, 2026 at 05:00 PM' },
    confirmation_status: 'confirmed',
    confirmation_token: 'CONF1234',
    confirmation_requested_at: '2026-11-14T10:00:00Z',
    confirmed_at: '2026-11-14T10:05:00Z',
    approval_status: 'pending',
    approved_by_id: null,
    approved_at: null,
    rejection_reason: null,
    clarification_notes: null,
    expires_at: '2026-11-14T11:00:00Z',
    error_message: null,
    created_at: '2026-11-14T10:00:00Z',
    updated_at: '2026-11-14T10:05:00Z',
    events: [
      {
        id: 'ev-1',
        workflow_id: 'wf-1',
        from_status: null,
        to_status: 'collecting_information',
        event_type: 'workflow_started',
        actor_type: 'deepti_agent',
        actor_id: null,
        payload: {},
        notes: 'Started book_appointment workflow',
        created_at: '2026-11-14T10:00:00Z',
      },
    ],
  },
];

jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    user: { id: 'u-1', email: 'op@physioone.com', full_name: 'Desk Op', role: { name: 'Operator' } },
    role: 'Operator',
    hasRole: () => true,
    hasPermission: () => true,
  }),
}));

describe('AppointmentsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(api, 'getAppointments').mockResolvedValue({
      appointments: mockAppointments,
      total: 1,
      page: 1,
      page_size: 20,
    });
    jest.spyOn(api, 'getAppointmentDetails').mockResolvedValue(mockAppointments[0]);
    jest.spyOn(api, 'getPendingApprovals').mockResolvedValue(mockWorkflows);
    jest.spyOn(api, 'getAppointmentWorkflows').mockResolvedValue({
      items: mockWorkflows,
      total: 1,
      page: 1,
      page_size: 20,
    });
    jest.spyOn(api, 'getAppointmentWorkflowSettings').mockResolvedValue({
      id: 'set-1',
      policy_mode: 'mode_a_read_only',
      require_patient_confirmation: true,
      workflow_expiry_minutes: 30,
      confirmation_expiry_minutes: 15,
      max_reschedule_count: 3,
      allow_cancellation_within_hours: 2,
      is_active: true,
      created_at: '2026-11-14T00:00:00Z',
      updated_at: '2026-11-14T00:00:00Z',
    });
    jest.spyOn(api, 'approveAppointmentWorkflow').mockResolvedValue({ success: true, result: {} });
    jest.spyOn(api, 'rejectAppointmentWorkflow').mockResolvedValue({ success: true, result: {} });
  });

  it('renders appointments page, displays Sunday closure policy and list of appointments', async () => {
    render(<AppointmentsPage />);

    // Header and Sunday closure alert
    expect(screen.getByText('Clinical Appointments')).toBeInTheDocument();
    expect(screen.getByText(/Sunday Closure Enforced/i)).toBeInTheDocument();

    // Appointment row
    await waitFor(() => {
      expect(screen.getByText('Ananya Sharma')).toBeInTheDocument();
      expect(screen.getByText('+919876543210')).toBeInTheDocument();
      expect(screen.getAllByText('Confirmed').length).toBeGreaterThan(0);
    });
  });

  it('opens appointment detail modal and shows lifecycle history', async () => {
    render(<AppointmentsPage />);

    await waitFor(() => {
      expect(screen.getByText('Ananya Sharma')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Details'));

    await waitFor(() => {
      expect(screen.getByText('Appointment Record & Audit Timeline')).toBeInTheDocument();
      expect(screen.getByText(/Lifecycle & Reschedule History/i)).toBeInTheDocument();
      expect(screen.getByText(/created/i)).toBeInTheDocument();
    });
  });

  it('opens Book Appointment dialog on button click', async () => {
    render(<AppointmentsPage />);

    fireEvent.click(screen.getByText('Book Appointment'));

    expect(screen.getByText('Book New Clinical Appointment')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. Ramesh Patel')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('+919876543210')).toBeInTheDocument();
  });

  it('switches to AI Approval Queue tab and renders pending proposals and policy banner', async () => {
    render(<AppointmentsPage />);

    const queueTab = screen.getByText('AI Approval Queue');
    expect(queueTab).toBeInTheDocument();

    fireEvent.click(queueTab);

    await waitFor(() => {
      expect(screen.getByText('Pending AI Appointment Proposals')).toBeInTheDocument();
      expect(screen.getByText('Rohan Mehra')).toBeInTheDocument();
      expect(screen.getByText('Confirmed by Patient')).toBeInTheDocument();
      expect(screen.getByText(/mode_a_read_only/i)).toBeInTheDocument();
    });
  });

  it('allows staff to approve a proposal from the approval queue', async () => {
    render(<AppointmentsPage />);

    fireEvent.click(screen.getByText('AI Approval Queue'));

    await waitFor(() => {
      expect(screen.getByText('Rohan Mehra')).toBeInTheDocument();
    });

    const approveBtn = screen.getByText('Approve');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText('Approve Appointment Proposal')).toBeInTheDocument();
      expect(screen.getByText('Confirm & Commit')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Confirm & Commit'));

    await waitFor(() => {
      expect(api.approveAppointmentWorkflow).toHaveBeenCalledWith('wf-1', expect.anything());
    });
  });

  it('switches to All AI Workflows tab and displays history', async () => {
    render(<AppointmentsPage />);

    fireEvent.click(screen.getByText('All AI Workflows'));

    await waitFor(() => {
      expect(screen.getByText('All AI Appointment Workflows')).toBeInTheDocument();
      expect(screen.getByText('Needs Staff Approval')).toBeInTheDocument();
    });
  });
});
