import React from 'react';
import { render, screen } from '@testing-library/react';
import DashboardLayout from './layout';

const mockReplace = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: jest.fn(),
  }),
  usePathname: () => '/dashboard',
}));

let mockAuthState: {
  user: any;
  role: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  logout: () => Promise<void>;
} = {
  user: {
    id: '1',
    email: 'admin@physioone.com',
    full_name: 'Admin User',
    is_active: true,
    role: { id: 'r1', name: 'Admin', is_system: true, description: 'Admin' },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  role: 'Admin',
  isLoading: false,
  isAuthenticated: true,
  logout: jest.fn(),
};

jest.mock('@/lib/auth-context', () => ({
  useAuth: () => mockAuthState,
}));

describe('DashboardLayout & Role-Based Navigation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders Admin navigation options (Campaigns & Staff visible, Clinic Settings hidden)', () => {
    mockAuthState = {
      user: {
        id: '1',
        email: 'admin@physioone.com',
        full_name: 'Admin User',
        is_active: true,
        role: { id: 'r1', name: 'Admin', is_system: true, description: 'Admin' },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      role: 'Admin',
      isLoading: false,
      isAuthenticated: true,
      logout: jest.fn(),
    };

    render(
      <DashboardLayout>
        <div>Content</div>
      </DashboardLayout>
    );

    // Dashboard, Live Inbox, Patients, Appointments, Campaigns, AI Agents, Staff & Roles should be present
    expect(screen.getByText('Campaigns')).toBeInTheDocument();
    expect(screen.getByText('Staff & Roles')).toBeInTheDocument();
    // Clinic Settings is Owner-only, so Admin must NOT see it
    expect(screen.queryByText('Clinic Settings')).not.toBeInTheDocument();
  });

  it('renders Operator navigation options (Campaigns & Staff hidden)', () => {
    mockAuthState = {
      user: {
        id: '2',
        email: 'op@physioone.com',
        full_name: 'Operator User',
        is_active: true,
        role: { id: 'r2', name: 'Operator', is_system: true, description: 'Operator' },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      role: 'Operator',
      isLoading: false,
      isAuthenticated: true,
      logout: jest.fn(),
    };

    render(
      <DashboardLayout>
        <div>Content</div>
      </DashboardLayout>
    );

    expect(screen.getByText('Live Inbox')).toBeInTheDocument();
    expect(screen.getByText('Appointments')).toBeInTheDocument();
    expect(screen.queryByText('Campaigns')).not.toBeInTheDocument();
    expect(screen.queryByText('Staff & Roles')).not.toBeInTheDocument();
    expect(screen.queryByText('Clinic Settings')).not.toBeInTheDocument();
  });

  it('redirects unauthenticated users to /login', () => {
    mockAuthState = {
      user: null as any,
      role: null,
      isLoading: false,
      isAuthenticated: false,
      logout: jest.fn(),
    };

    render(
      <DashboardLayout>
        <div>Protected</div>
      </DashboardLayout>
    );

    expect(mockReplace).toHaveBeenCalledWith('/login');
  });
});
