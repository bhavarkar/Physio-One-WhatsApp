import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginPage from './page';
import { api } from '@/lib/api-client';

const mockPush = jest.fn();
const mockReplace = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
  }),
}));

const mockLogin = jest.fn();
jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    login: mockLogin,
    isAuthenticated: false,
    user: null,
  }),
}));

describe('LoginPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(api, 'getSetupStatus').mockResolvedValue({
      is_initialized: true,
      owner_count: 1,
    });
  });

  it('renders login form elements with accessible inputs', async () => {
    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByText('Staff Sign In')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Staff Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password$/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign In to Console/i })).toBeInTheDocument();
  });

  it('toggles password visibility when clicking eye button', async () => {
    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/^Password$/i)).toBeInTheDocument();
    });

    const passwordInput = screen.getByLabelText(/^Password$/i);
    expect(passwordInput).toHaveAttribute('type', 'password');

    const toggleButton = screen.getByRole('button', { name: /Show password/i });
    fireEvent.click(toggleButton);

    expect(passwordInput).toHaveAttribute('type', 'text');
  });

  it('displays generic error on authentication rejection', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Unauthorized'));

    render(<LoginPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/Staff Email/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/Staff Email/i), {
      target: { value: 'unknown@physioone.com' },
    });
    fireEvent.change(screen.getByLabelText(/^Password$/i), {
      target: { value: 'incorrectpassword' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Sign In to Console/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Invalid email or password. Please verify your credentials./i)
      ).toBeInTheDocument();
    });
  });

  it('redirects to /setup if system is uninitialized', async () => {
    jest.spyOn(api, 'getSetupStatus').mockResolvedValueOnce({
      is_initialized: false,
      owner_count: 0,
    });

    render(<LoginPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith('/setup');
    });
  });
});
