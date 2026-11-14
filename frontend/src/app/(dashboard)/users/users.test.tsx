import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import UsersPage from './page';
import { api } from '@/lib/api-client';

const mockCurrentUser = {
  id: 'u-admin-1',
  email: 'admin@physioone.com',
  full_name: 'Admin Joe',
  is_active: true,
  role: { id: 'r-admin', name: 'Admin', is_system: true, description: 'Admin' },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    user: mockCurrentUser,
    role: 'Admin',
    hasRole: (r: string) => r === 'Admin',
  }),
}));

describe('UsersPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    jest.spyOn(api, 'getUsers').mockResolvedValue({
      users: [
        {
          id: 'u-owner-1',
          email: 'owner@physioone.com',
          full_name: 'Dr. Owner',
          is_active: true,
          role: { id: 'r-owner', name: 'Owner', is_system: true, description: 'Owner' },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: 'u-op-1',
          email: 'op@physioone.com',
          full_name: 'Operator Sam',
          is_active: true,
          role: { id: 'r-op', name: 'Operator', is_system: true, description: 'Operator' },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });

    jest.spyOn(api, 'getRoles').mockResolvedValue([
      { id: 'r-owner', name: 'Owner', is_system: true, description: 'Full access' },
      { id: 'r-admin', name: 'Admin', is_system: true, description: 'Admin access' },
      { id: 'r-op', name: 'Operator', is_system: true, description: 'Operator access' },
    ]);
  });

  it('renders staff list and prevents Admin from managing Owner accounts', async () => {
    render(<UsersPage />);

    await waitFor(() => {
      expect(screen.getByText('Dr. Owner')).toBeInTheDocument();
      expect(screen.getByText('Operator Sam')).toBeInTheDocument();
    });

    // The Owner row should display "Protected" for Admin user
    expect(screen.getByText('Protected')).toBeInTheDocument();
  });

  it('disables Owner option in Add Staff dialog when created by Admin to prevent privilege escalation', async () => {
    render(<UsersPage />);

    await waitFor(() => {
      expect(screen.getByText('Add Staff Member')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Add Staff Member'));

    await waitFor(() => {
      expect(screen.getByText('Provision an account for clinic operations. An initial secure password must be set.')).toBeInTheDocument();
    });

    // Look for the select element options
    const ownerOption = screen.getByText(/Owner \(Requires Owner role\)/i) as HTMLOptionElement;
    expect(ownerOption).toBeDisabled();
  });
});
