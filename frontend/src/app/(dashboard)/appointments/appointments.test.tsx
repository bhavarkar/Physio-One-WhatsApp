import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AppointmentsPage from './page';
import { api, Appointment } from '@/lib/api-client';

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
});
