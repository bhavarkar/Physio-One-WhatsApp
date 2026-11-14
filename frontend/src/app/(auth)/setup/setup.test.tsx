import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SetupPage from './page';
import { api } from '@/lib/api-client';

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
  }),
}));

const mockRefreshUser = jest.fn();
jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    refreshUser: mockRefreshUser,
  }),
}));

describe('SetupPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders setup form when system is uninitialized', async () => {
    jest.spyOn(api, 'getSetupStatus').mockResolvedValueOnce({
      is_initialized: false,
      owner_count: 0,
    });

    render(<SetupPage />);

    await waitFor(() => {
      expect(screen.getByText('Create Clinic Owner')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Full Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Clinic Administrator Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Master Password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Confirm Password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Initialize Clinic Platform/i })).toBeInTheDocument();
  });

  it('blocks access when system is already initialized', async () => {
    jest.spyOn(api, 'getSetupStatus').mockResolvedValueOnce({
      is_initialized: true,
      owner_count: 1,
    });

    render(<SetupPage />);

    await waitFor(() => {
      expect(screen.getByText('Setup Already Completed')).toBeInTheDocument();
    });

    expect(screen.queryByLabelText(/Master Password/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Return to Sign In/i })).toBeInTheDocument();
  });

  it('validates password mismatch before submission', async () => {
    jest.spyOn(api, 'getSetupStatus').mockResolvedValueOnce({
      is_initialized: false,
      owner_count: 0,
    });

    render(<SetupPage />);

    await waitFor(() => {
      expect(screen.getByText('Create Clinic Owner')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'Dr. Test' } });
    fireEvent.change(screen.getByLabelText(/Clinic Administrator Email/i), { target: { value: 'admin@test.com' } });
    fireEvent.change(screen.getByLabelText(/Master Password/i), { target: { value: 'password123' } });
    fireEvent.change(screen.getByLabelText(/Confirm Password/i), { target: { value: 'differentpassword' } });

    fireEvent.click(screen.getByRole('button', { name: /Initialize Clinic Platform/i }));

    await waitFor(() => {
      expect(screen.getByText('Passwords do not match.')).toBeInTheDocument();
    });
  });
});
