import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CampaignsPage from './page';
import {
  api,
  Campaign,
  CampaignMedia,
  CampaignAudiencePreview,
  CampaignImportReport,
  CampaignAnalytics,
  LegacyMigrationStatus,
  LegacyMigrationDryRun,
} from '@/lib/api-client';

const mockCampaigns: Campaign[] = [
  {
    id: 'camp-1',
    title: 'Post-Run Recovery Instagram Reel',
    description: 'Instagram re-engagement for knee rehabilitation inquiry leads',
    campaign_type: 'instagram_reengagement',
    status: 'draft',
    provider: 'meta',
    is_approved: false,
    current_version: 1,
    rate_limit_per_minute: 30,
    rate_limit_per_hour: 500,
    batch_size: 25,
    cooldown_days: 7,
    execution_window_start: '09:00',
    execution_window_end: '21:00',
    template_name: 'reengagement_reel_v1',
    custom_message_body: 'Hi {{name}}, check out our latest Instagram reel.',
    target_audience_rules: {
      interaction_window_hours: [24, 48],
      require_marketing_consent: true,
      exclude_already_booked: true,
    },
    total_recipients: 10,
    total_sent: 5,
    total_delivered: 4,
    total_read: 3,
    total_converted: 1,
    total_suppressed: 5,
    total_failed: 0,
    created_at: '2026-11-14T10:00:00Z',
    updated_at: '2026-11-14T10:00:00Z',
  },
  {
    id: 'camp-2',
    title: 'Awaiting Review Campaign',
    campaign_type: 'patient_education',
    status: 'awaiting_approval',
    provider: 'ycloud',
    is_approved: false,
    current_version: 2,
    rate_limit_per_minute: 30,
    rate_limit_per_hour: 500,
    batch_size: 25,
    cooldown_days: 7,
    execution_window_start: '09:00',
    execution_window_end: '21:00',
    template_name: 'education_v1',
    custom_message_body: 'Important tips for ACL injury recovery.',
    target_audience_rules: {},
    total_recipients: 0,
    total_sent: 0,
    total_delivered: 0,
    total_read: 0,
    total_converted: 0,
    total_suppressed: 0,
    total_failed: 0,
    created_at: '2026-11-14T11:00:00Z',
    updated_at: '2026-11-14T11:00:00Z',
  },
];

const mockMedia: CampaignMedia[] = [
  {
    id: 'med-1',
    title: 'Hamstring & Knee Protocol',
    media_type: 'instagram_reel',
    instagram_url: 'https://www.instagram.com/reel/Cxyz123/',
    caption: 'Therapeutic mobility drills for post-run knee pain',
    tags: ['hamstring', 'kneepain'],
    is_active: true,
    created_at: '2026-11-14T09:00:00Z',
    updated_at: '2026-11-14T09:00:00Z',
  },
];

const mockMigrationStatus: LegacyMigrationStatus = {
  cutover_state: 'shadow_comparison',
  legacy_system_name: 'Physio One n8n / YCloud',
  last_dry_run_at: '2026-11-14T15:00:00Z',
  dry_run_discrepancy_count: 0,
  is_live_dispatch_blocked: true,
  notes: 'Dry-run comparison running cleanly in shadow mode',
};

const mockPreview: CampaignAudiencePreview = {
  campaign_id: 'camp-1',
  total_evaluated: 12,
  eligible_count: 7,
  suppressed_count: 5,
  suppression_breakdown: {
    missing_marketing_consent: 3,
    contact_opted_out_all: 1,
    appointment_already_booked: 1,
  },
  sample_eligible_recipients: [
    {
      contact_id: 'c-1',
      wa_id: '919876543210',
      name: 'Ananya Sharma',
      last_active_at: '2026-11-13T10:00:00Z',
    },
  ],
  sample_rendered_message: 'Hi Ananya, Dr. Physio One shared our latest knee recovery reel: https://instagram.com/reel/Cxyz123/. Reply to book an assessment.',
};

const mockAnalytics: CampaignAnalytics = {
  campaign_id: 'camp-1',
  title: 'Post-Run Recovery Instagram Reel',
  campaign_type: 'instagram_reengagement',
  status: 'running',
  total_recipients: 10,
  total_sent: 5,
  total_delivered: 4,
  total_read: 3,
  total_converted: 1,
  total_suppressed: 5,
  total_failed: 0,
  delivery_rate_pct: 80,
  read_rate_pct: 60,
  conversion_rate_pct: 20,
  failure_rate_pct: 0,
  attribution_window_hours: 72,
  suppression_breakdown: { missing_marketing_consent: 3 },
};

const mockDryRun: LegacyMigrationDryRun = {
  total_evaluated: 20,
  legacy_predicted_count: 8,
  new_engine_eligible_count: 8,
  discrepancy_count: 0,
  suppression_summary: { missing_consent: 5 },
  discrepancies: [],
};

const mockImportReport: CampaignImportReport = {
  total_rows: 2,
  accepted_count: 2,
  rejected_count: 0,
  duplicate_count: 0,
  created_contacts_count: 1,
  rejections: [],
};

jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    user: {
      id: 'u-admin',
      email: 'admin@physioone.com',
      full_name: 'Clinic Owner',
      role: { name: 'owner' },
    },
    role: 'owner',
    hasRole: () => true,
    hasPermission: () => true,
  }),
}));

describe('CampaignsPage (Task 12)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(api, 'getCampaigns').mockResolvedValue({ items: mockCampaigns, total: 2 });
    jest.spyOn(api, 'getCampaignMedia').mockResolvedValue({ items: mockMedia, total: 1 });
    jest.spyOn(api, 'getLegacyMigrationStatus').mockResolvedValue(mockMigrationStatus);
    jest.spyOn(api, 'createCampaign').mockResolvedValue({ ...mockCampaigns[0], id: 'camp-new' });
    jest.spyOn(api, 'previewCampaignAudience').mockResolvedValue(mockPreview);
    jest.spyOn(api, 'approveCampaign').mockResolvedValue({ ...mockCampaigns[1], is_approved: true, status: 'approved' });
    jest.spyOn(api, 'getCampaignAnalytics').mockResolvedValue(mockAnalytics);
    jest.spyOn(api, 'getCampaignRecipients').mockResolvedValue({ items: [], total: 0 });
    jest.spyOn(api, 'runLegacyDryRun').mockResolvedValue(mockDryRun);
    jest.spyOn(api, 'importCampaignCsv').mockResolvedValue(mockImportReport);
  });

  test('1. Renders page title, safe mode notice, and overview cards', async () => {
    render(<CampaignsPage />);
    expect(screen.getByText('Instagram Re-engagement & Campaigns')).toBeInTheDocument();
    expect(screen.getByText(/Safe Operational Mode Active/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Post-Run Recovery Instagram Reel')).toBeInTheDocument();
    });

    expect(screen.getByText('Total Campaigns')).toBeInTheDocument();
    expect(screen.getAllByText('Awaiting Approval')[0]).toBeInTheDocument();
  });

  test('2. Filters campaigns by search query', async () => {
    render(<CampaignsPage />);
    await waitFor(() => {
      expect(screen.getByText('Post-Run Recovery Instagram Reel')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search campaigns by title or template...');
    fireEvent.change(searchInput, { target: { value: 'Awaiting' } });

    expect(screen.getByText('Awaiting Review Campaign')).toBeInTheDocument();
    expect(screen.queryByText('Post-Run Recovery Instagram Reel')).not.toBeInTheDocument();
  });

  test('3. Opens and submits New Campaign form', async () => {
    render(<CampaignsPage />);
    const newBtn = screen.getByRole('button', { name: /New Campaign/i });
    fireEvent.click(newBtn);

    expect(screen.getByText('Create New Campaign')).toBeInTheDocument();
    const titleInput = screen.getByPlaceholderText(/e\.g\. November Knee Pain/i);
    fireEvent.change(titleInput, { target: { value: 'Brand New Test Campaign' } });

    const submitBtn = screen.getByRole('button', { name: /Create Campaign \(Draft\)/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(api.createCampaign).toHaveBeenCalled();
    });
  });

  test('4. Previews audience with suppression gates breakdown', async () => {
    render(<CampaignsPage />);
    await waitFor(() => {
      expect(screen.getByText('Post-Run Recovery Instagram Reel')).toBeInTheDocument();
    });

    const previewButtons = screen.getAllByTitle('Preview Audience & Message');
    fireEvent.click(previewButtons[0]);

    await waitFor(() => {
      expect(screen.getByText('Audience & Template Preview')).toBeInTheDocument();
      expect(screen.getByText('Sample Rendered Message:')).toBeInTheDocument();
      expect(screen.getByText(/Hi Ananya, Dr. Physio One/i)).toBeInTheDocument();
    });
  });

  test('5. Switches to Approval Queue tab and processes campaign approval', async () => {
    render(<CampaignsPage />);
    await waitFor(() => {
      expect(screen.getByText('Post-Run Recovery Instagram Reel')).toBeInTheDocument();
    });

    const approvalsTab = screen.getByRole('button', { name: /Approval Queue/i });
    fireEvent.click(approvalsTab);

    expect(screen.getByText('Immutable Campaign Approval Queue')).toBeInTheDocument();
    expect(screen.getByText('Awaiting Review Campaign')).toBeInTheDocument();

    const approveBtn = screen.getByRole('button', { name: /Approve Campaign/i });
    fireEvent.click(approveBtn);

    expect(screen.getByText('Campaign Authorization Review')).toBeInTheDocument();
    const confirmBtn = screen.getByRole('button', { name: /Confirm Approval/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.approveCampaign).toHaveBeenCalledWith('camp-2', 'approve', undefined);
    });
  });

  test('6. Switches to Instagram Reel Library tab and shows reels', async () => {
    render(<CampaignsPage />);
    const mediaTab = screen.getByRole('button', { name: /Instagram Reel Library/i });
    fireEvent.click(mediaTab);

    await waitFor(() => {
      expect(screen.getByText('Hamstring & Knee Protocol')).toBeInTheDocument();
      expect(screen.getByText('View Instagram Post')).toBeInTheDocument();
      expect(screen.getByText('#hamstring')).toBeInTheDocument();
    });
  });

  test('7. Switches to Legacy YCloud Cutover tab and triggers dry run comparison', async () => {
    render(<CampaignsPage />);
    await waitFor(() => {
      expect(screen.getByText('Post-Run Recovery Instagram Reel')).toBeInTheDocument();
    });

    const migTab = screen.getByRole('button', { name: /Legacy YCloud Cutover/i });
    fireEvent.click(migTab);

    expect(screen.getByText(/Mutual Exclusion Invariant Enforced/i)).toBeInTheDocument();
    expect(screen.getByText(/Blocked \(Mutual Exclusion\)/i)).toBeInTheDocument();

    const dryRunBtn = screen.getByRole('button', { name: /Run Dry-Run Comparison/i });
    fireEvent.click(dryRunBtn);

    await waitFor(() => {
      expect(api.runLegacyDryRun).toHaveBeenCalled();
      expect(screen.getByText('n8n vs New Engine Dry-Run Comparison')).toBeInTheDocument();
      expect(screen.getByText(/100% targeting match/i)).toBeInTheDocument();
    });
  });

  test('8. Switches to Contact CSV Import tab and imports contact batch', async () => {
    render(<CampaignsPage />);
    const csvTab = screen.getByRole('button', { name: /Contact CSV Import/i });
    fireEvent.click(csvTab);

    expect(screen.getByText('Contact List CSV Import & Normalization')).toBeInTheDocument();
    const importBtn = screen.getByRole('button', { name: /Import CSV Contacts/i });
    fireEvent.click(importBtn);

    await waitFor(() => {
      expect(api.importCampaignCsv).toHaveBeenCalled();
      expect(screen.getByText('CSV Import Execution Summary')).toBeInTheDocument();
    });
  });
});
