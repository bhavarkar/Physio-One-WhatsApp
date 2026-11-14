import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SettingsPage from './page';
import { api } from '@/lib/api-client';

const mockConnections = [
  {
    id: 'conn-meta-1',
    provider: 'meta' as const,
    account_name: 'Physio One Primary',
    phone_number_id: 'meta-phone-123',
    business_account_id: 'meta-waba-456',
    display_phone_number: '+919876543210',
    webhook_verify_token: 'meta_verify_token_123',
    has_access_token: true,
    has_secret_key: true,
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'conn-ycloud-2',
    provider: 'ycloud' as const,
    account_name: 'Physio One Legacy YCloud',
    phone_number_id: 'ycloud-id-789',
    business_account_id: null,
    display_phone_number: '+919123456789',
    webhook_verify_token: 'ycloud_verify_token_456',
    has_access_token: true,
    has_secret_key: false,
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

describe('SettingsPage - WhatsApp Connections', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(api, 'getWhatsAppConnections').mockResolvedValue(mockConnections);
  });

  it('renders WhatsApp connection settings and lists existing connections', async () => {
    render(<SettingsPage />);

    expect(screen.getByText(/Loading WhatsApp connections.../i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('System Settings & WhatsApp Integrations')).toBeInTheDocument();
      expect(screen.getByText('+919876543210')).toBeInTheDocument();
      expect(screen.getByText('Physio One Primary')).toBeInTheDocument();
      expect(screen.getByText('+919123456789')).toBeInTheDocument();
      expect(screen.getByText('Physio One Legacy YCloud')).toBeInTheDocument();
      expect(screen.getByText('Meta Cloud API')).toBeInTheDocument();
      expect(screen.getByText('YCloud API')).toBeInTheDocument();
    });

    // Verify secrets are NOT displayed in plaintext
    expect(screen.queryByText('EAAG...')).not.toBeInTheDocument();
    expect(screen.getAllByText(/Encrypted at rest \(Fernet AES-128\)/i).length).toBe(2);
  });

  it('opens Add Connection modal and allows provider selection', async () => {
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByText('Add Connection')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Add Connection'));

    expect(screen.getByText('Configure WhatsApp Provider')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('+919876543210')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Custom alphanumeric verification token')).toBeInTheDocument();

    // Provider selection
    const ycloudBtn = screen.getByRole('button', { name: /YCloud Provider/i });
    fireEvent.click(ycloudBtn);
    expect(ycloudBtn).toHaveClass('bg-emerald-50');
  });

  it('performs provider handshake test and displays result', async () => {
    jest.spyOn(api, 'testWhatsAppConnection').mockResolvedValue({
      is_valid: true,
      display_name: 'Physio One Clinic',
      phone_number: '+919876543210',
      error: null,
    });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /Handshake/i })[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: /Handshake/i })[0]);

    await waitFor(() => {
      expect(screen.getByText(/Provider Handshake: VALID/i)).toBeInTheDocument();
      expect(screen.getByText(/Successfully validated connection for Physio One Clinic/i)).toBeInTheDocument();
    });
  });
});

