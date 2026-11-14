'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import {
  api,
  Campaign,
  CampaignMedia,
  CampaignRecipient,
  CampaignAudiencePreview,
  CampaignImportReport,
  CampaignAnalytics,
  LegacyMigrationStatus,
  LegacyMigrationDryRun,
} from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Dialog } from '@/components/ui/dialog';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/table';
import {
  Megaphone,
  Video,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  Pause,
  RotateCcw,
  RefreshCw,
  Plus,
  ShieldCheck,
  ShieldAlert,
  Clock,
  Eye,
  Calendar,
  Search,
  Upload,
  ArrowRightLeft,
  FileSpreadsheet,
  ExternalLink,
  Users,
  Check,
  X,
  Send,
  BarChart2,
} from 'lucide-react';

function formatISTDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(d);
  } catch {
    return isoString;
  }
}

export default function CampaignsPage() {
  const { user } = useAuth();
  const isOwnerOrAdmin = user?.role?.name === 'owner' || user?.role?.name === 'admin';

  // Navigation tab
  const [activeTab, setActiveTab] = useState<'campaigns' | 'approvals' | 'media' | 'migration' | 'csv_import'>('campaigns');

  // Data states
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [mediaList, setMediaList] = useState<CampaignMedia[]>([]);
  const [migrationStatus, setMigrationStatus] = useState<LegacyMigrationStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<CampaignAudiencePreview | null>(null);
  const [activeCampaign, setActiveCampaign] = useState<Campaign | null>(null);

  const [isAnalyticsOpen, setIsAnalyticsOpen] = useState(false);
  const [analyticsData, setAnalyticsData] = useState<CampaignAnalytics | null>(null);
  const [analyticsRecipients, setAnalyticsRecipients] = useState<CampaignRecipient[]>([]);

  const [isAddMediaOpen, setIsAddMediaOpen] = useState(false);
  const [mediaForm, setMediaForm] = useState({
    title: '',
    media_type: 'instagram_reel',
    instagram_url: '',
    caption: '',
    tags: '',
  });

  const [isDryRunOpen, setIsDryRunOpen] = useState(false);
  const [dryRunData, setDryRunData] = useState<LegacyMigrationDryRun | null>(null);
  const [isDryRunning, setIsDryRunning] = useState(false);

  const [isCutoverModalOpen, setIsCutoverModalOpen] = useState(false);
  const [selectedCutoverState, setSelectedCutoverState] = useState<string>('legacy_active');
  const [cutoverNotes, setCutoverNotes] = useState('');

  // CSV Import state
  const [csvText, setCsvText] = useState(
    'name,phone,marketing_consent\nAnanya Sharma,+919876543210,true\nRahul Verma,+919811223344,yes\n'
  );
  const [csvReport, setCsvReport] = useState<CampaignImportReport | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  // Approval review notes
  const [approvalNotes, setApprovalNotes] = useState('');
  const [selectedCampaignForApproval, setSelectedCampaignForApproval] = useState<Campaign | null>(null);
  const [isApprovalDialogOpen, setIsApprovalDialogOpen] = useState(false);
  const [approvalDecision, setApprovalDecision] = useState<'approve' | 'reject'>('approve');

  // Create Campaign Form
  const [campaignForm, setCampaignForm] = useState({
    title: '',
    description: '',
    campaign_type: 'instagram_reengagement',
    provider: 'meta',
    media_id: '',
    template_name: 'reengagement_reel_v1',
    custom_message_body: 'Hi {{name}}, Dr. Physio One shared a specialized recovery reel for your recent inquiry: {{reel_url}}. Need a follow-up assessment? Reply to book.',
    min_hours: 24,
    max_hours: 48,
    require_marketing_consent: true,
    exclude_already_booked: true,
    execution_window_start: '09:00',
    execution_window_end: '21:00',
    rate_limit_per_minute: 30,
    rate_limit_per_hour: 500,
    batch_size: 25,
    cooldown_days: 7,
  });

  // Load all initial data
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [cRes, mRes, migRes] = await Promise.all([
        api.getCampaigns({ limit: 100 }),
        api.getCampaignMedia(),
        api.getLegacyMigrationStatus().catch(() => null),
      ]);
      setCampaigns(cRes.items || []);
      setMediaList(mRes.items || []);
      if (migRes) setMigrationStatus(migRes);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load campaign data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Derived counts
  const totalCampaigns = campaigns.length;
  const draftCount = campaigns.filter((c) => c.status === 'draft' || c.status === 'audience_prepared').length;
  const awaitingApprovalCount = campaigns.filter((c) => c.status === 'awaiting_approval').length;
  const activeCount = campaigns.filter((c) => c.status === 'scheduled' || c.status === 'running').length;
  const completedCount = campaigns.filter((c) => c.status === 'completed').length;

  const totalDelivered = campaigns.reduce((acc, c) => acc + (c.total_delivered || 0), 0);
  const totalConverted = campaigns.reduce((acc, c) => acc + (c.total_converted || 0), 0);

  // Filtered campaigns
  const filteredCampaigns = campaigns.filter((c) => {
    const matchesSearch =
      c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (c.template_name && c.template_name.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
    const matchesType = typeFilter === 'all' || c.campaign_type === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });

  // Handle Create Campaign
  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const payload = {
        title: campaignForm.title,
        description: campaignForm.description || undefined,
        campaign_type: campaignForm.campaign_type,
        provider: campaignForm.provider,
        media_id: campaignForm.media_id || undefined,
        template_name: campaignForm.template_name,
        custom_message_body: campaignForm.custom_message_body,
        execution_window_start: campaignForm.execution_window_start,
        execution_window_end: campaignForm.execution_window_end,
        rate_limit_per_minute: Number(campaignForm.rate_limit_per_minute),
        rate_limit_per_hour: Number(campaignForm.rate_limit_per_hour),
        batch_size: Number(campaignForm.batch_size),
        cooldown_days: Number(campaignForm.cooldown_days),
        target_audience_rules: {
          interaction_window_hours: [Number(campaignForm.min_hours), Number(campaignForm.max_hours)],
          require_marketing_consent: campaignForm.require_marketing_consent,
          exclude_already_booked: campaignForm.exclude_already_booked,
          cooldown_days: Number(campaignForm.cooldown_days),
        },
      };

      await api.createCampaign(payload);
      setSuccessMessage('Campaign created in Draft status. You can now preview the audience.');
      setIsCreateOpen(false);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create campaign');
    }
  };

  // Handle Preview Audience
  const handlePreviewAudience = async (camp: Campaign, persist: boolean = false) => {
    setError(null);
    try {
      setActiveCampaign(camp);
      const res = await api.previewCampaignAudience(camp.id, persist);
      setPreviewData(res);
      setIsPreviewOpen(true);
      if (persist) {
        await loadData();
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to evaluate audience');
    }
  };

  // Submit campaign for approval
  const handleSubmitForApproval = async (camp: Campaign) => {
    setError(null);
    try {
      await api.updateCampaign(camp.id, { status: 'awaiting_approval' });
      setSuccessMessage(`Campaign "${camp.title}" submitted for Owner/Admin approval.`);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to submit campaign for approval');
    }
  };

  // Open Approval Dialog
  const openApprovalDialog = (camp: Campaign, decision: 'approve' | 'reject') => {
    setSelectedCampaignForApproval(camp);
    setApprovalDecision(decision);
    setApprovalNotes('');
    setIsApprovalDialogOpen(true);
  };

  // Handle Approve / Reject
  const handleApprovalAction = async () => {
    if (!selectedCampaignForApproval) return;
    setError(null);
    try {
      await api.approveCampaign(selectedCampaignForApproval.id, approvalDecision, approvalNotes || undefined);
      setSuccessMessage(
        approvalDecision === 'approve'
          ? `Campaign "${selectedCampaignForApproval.title}" approved successfully.`
          : `Campaign "${selectedCampaignForApproval.title}" rejected.`
      );
      setIsApprovalDialogOpen(false);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to process approval');
    }
  };

  // Handle Schedule Campaign
  const handleScheduleCampaign = async (camp: Campaign) => {
    setError(null);
    try {
      await api.scheduleCampaign(camp.id);
      setSuccessMessage(`Campaign "${camp.title}" scheduled for 09:00 - 21:00 IST automated sending.`);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to schedule campaign');
    }
  };

  // Handle Pause / Resume / Cancel
  const handlePauseCampaign = async (camp: Campaign) => {
    try {
      await api.pauseCampaign(camp.id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to pause campaign');
    }
  };

  const handleResumeCampaign = async (camp: Campaign) => {
    try {
      await api.resumeCampaign(camp.id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to resume campaign');
    }
  };

  const handleCancelCampaign = async (camp: Campaign) => {
    if (!window.confirm(`Are you sure you want to cancel "${camp.title}"? This cannot be undone.`)) return;
    try {
      await api.cancelCampaign(camp.id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel campaign');
    }
  };

  // Open Analytics Modal
  const handleOpenAnalytics = async (camp: Campaign) => {
    setError(null);
    try {
      setActiveCampaign(camp);
      const [analytics, recips] = await Promise.all([
        api.getCampaignAnalytics(camp.id),
        api.getCampaignRecipients(camp.id, { limit: 50 }),
      ]);
      setAnalyticsData(analytics);
      setAnalyticsRecipients(recips.items || []);
      setIsAnalyticsOpen(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load campaign analytics');
    }
  };

  // Handle Add Media
  const handleAddMedia = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const tagsArray = mediaForm.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      await api.createCampaignMedia({
        title: mediaForm.title,
        media_type: mediaForm.media_type,
        instagram_url: mediaForm.instagram_url || undefined,
        caption: mediaForm.caption || undefined,
        tags: tagsArray.length ? tagsArray : undefined,
      });

      setSuccessMessage('Instagram Reel media added to approved library.');
      setIsAddMediaOpen(false);
      setMediaForm({ title: '', media_type: 'instagram_reel', instagram_url: '', caption: '', tags: '' });
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add media');
    }
  };

  // Handle Delete / Archive Media
  const handleDeleteMedia = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete/archive this media item?')) return;
    try {
      await api.deleteCampaignMedia(id);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete media');
    }
  };

  // Handle Dry Run
  const handleRunDryRun = async () => {
    setIsDryRunning(true);
    setError(null);
    try {
      const res = await api.runLegacyDryRun();
      setDryRunData(res);
      setIsDryRunOpen(true);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to execute dry-run comparison');
    } finally {
      setIsDryRunning(false);
    }
  };

  // Handle Cutover State Change
  const handleSetCutoverState = async () => {
    setError(null);
    try {
      await api.setLegacyCutoverState({
        cutover_state: selectedCutoverState,
        notes: cutoverNotes || undefined,
      });
      setSuccessMessage(`Migration cutover state transitioned to "${selectedCutoverState}".`);
      setIsCutoverModalOpen(false);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update cutover state');
    }
  };

  // Handle CSV Import
  const handleImportCsv = async () => {
    setIsImporting(true);
    setError(null);
    try {
      const res = await api.importCampaignCsv(csvText);
      setCsvReport(res);
      setSuccessMessage(`Import completed: ${res.accepted_count} contacts accepted, ${res.created_contacts_count} created.`);
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to import CSV');
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Instagram Re-engagement & Campaigns
          </h1>
          <p className="text-sm text-slate-500">
            Automated 09:00–21:00 IST Instagram reel re-engagement, controlled broadcasts, and legacy YCloud migration.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadData} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setIsCreateOpen(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white">
            <Plus className="h-4 w-4 mr-2" />
            New Campaign
          </Button>
        </div>
      </div>

      {/* Safety & Kill Switch Banner */}
      <div className="p-4 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-3">
        <ShieldAlert className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <p className="font-semibold text-amber-950">Safe Operational Mode Active (Automated Kill Switch Enforced)</p>
          <p>
            Outbound automated dispatches remain strictly suppressed until explicitly authorized. All created campaigns default to
            <span className="font-mono bg-amber-100 px-1 py-0.5 rounded mx-1">draft</span> and require immutable Owner/Admin approval before scheduling.
            Targeting strictly enforces the 24–48h interaction window, 09:00–21:00 IST business hours, and marketing consent.
          </p>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <Alert variant="destructive" title="Campaign System Alert">
          {error}
        </Alert>
      )}
      {successMessage && (
        <Alert variant="success" title="Success">
          {successMessage}
        </Alert>
      )}

      {/* KPI Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500">Total Campaigns</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{totalCampaigns}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">Across all categories</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500">Drafts / In-Prep</div>
            <div className="text-2xl font-bold text-amber-600 mt-1">{draftCount}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">Requires audience prep</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500">Awaiting Approval</div>
            <div className="text-2xl font-bold text-purple-600 mt-1">{awaitingApprovalCount}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">Owner/Admin review</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500">Scheduled / Running</div>
            <div className="text-2xl font-bold text-emerald-600 mt-1">{activeCount}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">09:00–21:00 IST cycle</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500">Delivered Total</div>
            <div className="text-2xl font-bold text-sky-600 mt-1">{totalDelivered}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">WhatsApp receipts</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500">Conversions (72h)</div>
            <div className="text-2xl font-bold text-indigo-600 mt-1">{totalConverted}</div>
            <div className="text-[11px] text-slate-400 mt-0.5">Booked appointments</div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-slate-200 gap-2">
        <button
          onClick={() => setActiveTab('campaigns')}
          className={`flex items-center gap-2 pb-3 px-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'campaigns'
              ? 'border-emerald-600 text-emerald-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Megaphone className="h-4 w-4" />
          Campaigns & Broadcasts
          <span className="ml-1 text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
            {campaigns.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('approvals')}
          className={`flex items-center gap-2 pb-3 px-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'approvals'
              ? 'border-purple-600 text-purple-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <ShieldCheck className="h-4 w-4" />
          Approval Queue
          {awaitingApprovalCount > 0 && (
            <span className="ml-1 text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-semibold">
              {awaitingApprovalCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('media')}
          className={`flex items-center gap-2 pb-3 px-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'media'
              ? 'border-sky-600 text-sky-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Video className="h-4 w-4" />
          Instagram Reel Library
          <span className="ml-1 text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
            {mediaList.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab('migration')}
          className={`flex items-center gap-2 pb-3 px-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'migration'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <ArrowRightLeft className="h-4 w-4" />
          Legacy YCloud Cutover
          {migrationStatus && (
            <span className="ml-1 text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">
              {migrationStatus.cutover_state}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('csv_import')}
          className={`flex items-center gap-2 pb-3 px-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'csv_import'
              ? 'border-emerald-600 text-emerald-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileSpreadsheet className="h-4 w-4" />
          Contact CSV Import
        </button>
      </div>

      {/* TAB 1: CAMPAIGNS LIST */}
      {activeTab === 'campaigns' && (
        <div className="space-y-4">
          {/* Search & Filter Bar */}
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search campaigns by title or template..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="px-3 py-2 text-sm border rounded-md bg-white text-slate-700"
            >
              <option value="all">All Campaign Types</option>
              <option value="instagram_reengagement">Instagram Re-engagement</option>
              <option value="patient_education">Patient Education</option>
              <option value="seasonal_broadcast">Seasonal Broadcast</option>
              <option value="custom_broadcast">Custom Broadcast</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 text-sm border rounded-md bg-white text-slate-700"
            >
              <option value="all">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="audience_prepared">Audience Prepared</option>
              <option value="awaiting_approval">Awaiting Approval</option>
              <option value="approved">Approved</option>
              <option value="scheduled">Scheduled</option>
              <option value="running">Running</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          {/* Campaigns Table */}
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Campaign</TableHead>
                  <TableHead>Type & Provider</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Approval</TableHead>
                  <TableHead>Recipients</TableHead>
                  <TableHead>Performance</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCampaigns.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-10 text-slate-500 text-sm">
                      No campaigns found matching criteria. Create one using "New Campaign".
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredCampaigns.map((camp) => (
                    <TableRow key={camp.id}>
                      <TableCell>
                        <div className="font-semibold text-slate-900 text-sm">{camp.title}</div>
                        <div className="text-xs text-slate-500">
                          Template: <span className="font-mono">{camp.template_name || 'inline'}</span> (v{camp.current_version})
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-xs font-medium text-slate-800">
                          {camp.campaign_type.replace('_', ' ')}
                        </div>
                        <Badge variant="outline" className="text-[10px] mt-0.5 uppercase">
                          {camp.provider}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            camp.status === 'scheduled' || camp.status === 'running'
                              ? 'success'
                              : camp.status === 'awaiting_approval'
                              ? 'warning'
                              : camp.status === 'cancelled'
                              ? 'destructive'
                              : 'secondary'
                          }
                          className="capitalize text-xs"
                        >
                          {camp.status.replace('_', ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {camp.is_approved ? (
                          <div className="flex items-center text-xs text-emerald-700 gap-1 font-medium">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Approved (v{camp.approved_version})
                          </div>
                        ) : (
                          <div className="flex items-center text-xs text-amber-700 gap-1">
                            <Clock className="h-3.5 w-3.5" />
                            Unapproved
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="text-xs text-slate-900 font-medium">
                          {camp.total_recipients || 0} evaluated
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {camp.total_sent} sent / {camp.total_suppressed} suppressed
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-xs text-slate-900 font-medium">
                          {camp.total_delivered} delivered ({camp.total_read} read)
                        </div>
                        <div className="text-[11px] text-indigo-600 font-medium">
                          {camp.total_converted} converted
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handlePreviewAudience(camp, false)}
                            title="Preview Audience & Message"
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleOpenAnalytics(camp)}
                            title="Analytics & Recipients"
                          >
                            <BarChart2 className="h-4 w-4 text-indigo-600" />
                          </Button>

                          {/* Approval / Submit Actions */}
                          {(camp.status === 'draft' || camp.status === 'audience_prepared') && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleSubmitForApproval(camp)}
                              className="text-xs text-purple-700 border-purple-200 hover:bg-purple-50"
                            >
                              Submit
                            </Button>
                          )}

                          {camp.status === 'approved' && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleScheduleCampaign(camp)}
                              className="text-xs text-emerald-700 border-emerald-200 hover:bg-emerald-50"
                            >
                              Schedule
                            </Button>
                          )}

                          {camp.status === 'running' && (
                            <Button variant="ghost" size="sm" onClick={() => handlePauseCampaign(camp)} title="Pause">
                              <Pause className="h-4 w-4 text-amber-600" />
                            </Button>
                          )}

                          {camp.status === 'paused' && (
                            <Button variant="ghost" size="sm" onClick={() => handleResumeCampaign(camp)} title="Resume">
                              <Play className="h-4 w-4 text-emerald-600" />
                            </Button>
                          )}

                          {(camp.status === 'scheduled' || camp.status === 'running' || camp.status === 'paused') && (
                            <Button variant="ghost" size="sm" onClick={() => handleCancelCampaign(camp)} title="Cancel">
                              <XCircle className="h-4 w-4 text-red-500" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}

      {/* TAB 2: APPROVAL QUEUE */}
      {activeTab === 'approvals' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-purple-600" />
                Immutable Campaign Approval Queue
              </CardTitle>
              <CardDescription>
                Campaigns awaiting Owner/Admin authorization. Re-approval is strictly required whenever audience rules, media, or copy are updated.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!isOwnerOrAdmin && (
                <Alert variant="info" title="Permission Notice" className="mb-4">
                  You are viewing this queue with read-only permissions. Only Owner and Admin users can submit approvals or rejections.
                </Alert>
              )}

              {campaigns.filter((c) => c.status === 'awaiting_approval').length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-sm">
                  <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto mb-2" />
                  No campaigns currently awaiting review. All submissions are up to date.
                </div>
              ) : (
                <div className="space-y-4">
                  {campaigns
                    .filter((c) => c.status === 'awaiting_approval')
                    .map((camp) => (
                      <div key={camp.id} className="p-4 border rounded-lg bg-slate-50/50 space-y-3">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <div>
                            <div className="font-semibold text-slate-900 text-base">{camp.title}</div>
                            <div className="text-xs text-slate-500">
                              Type: <span className="font-medium text-slate-700">{camp.campaign_type}</span> | Provider:{' '}
                              <span className="uppercase font-medium text-slate-700">{camp.provider}</span> | Version Snapshot:{' '}
                              <span className="font-mono text-purple-700">v{camp.current_version}</span>
                            </div>
                          </div>
                          {isOwnerOrAdmin && (
                            <div className="flex items-center gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openApprovalDialog(camp, 'reject')}
                                className="text-xs text-red-700 border-red-200 hover:bg-red-50"
                              >
                                Reject
                              </Button>
                              <Button
                                size="sm"
                                onClick={() => openApprovalDialog(camp, 'approve')}
                                className="text-xs bg-purple-600 hover:bg-purple-700 text-white"
                              >
                                <Check className="h-4 w-4 mr-1" />
                                Approve Campaign
                              </Button>
                            </div>
                          )}
                        </div>

                        {/* Audience and Target Rules Summary */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs bg-white p-3 rounded border">
                          <div>
                            <span className="text-slate-500 block">Sending Window:</span>
                            <span className="font-medium text-slate-800">
                              {camp.execution_window_start} – {camp.execution_window_end} IST
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Rate Limits:</span>
                            <span className="font-medium text-slate-800">
                              {camp.rate_limit_per_minute}/min ({camp.rate_limit_per_hour}/hr)
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block">Cooldown & Batch:</span>
                            <span className="font-medium text-slate-800">
                              {camp.cooldown_days} days cooldown | batch size {camp.batch_size}
                            </span>
                          </div>
                        </div>

                        {/* Message Preview */}
                        <div className="p-3 bg-slate-100 rounded text-xs font-mono text-slate-800 border">
                          <span className="text-slate-500 block text-[10px] font-sans uppercase mb-1">
                            Message Copy / Template
                          </span>
                          {camp.custom_message_body || `Template: ${camp.template_name}`}
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 3: MEDIA LIBRARY */}
      {activeTab === 'media' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">
              Curated Instagram Reels and multimedia library with URL validation, tags, and secure previews.
            </p>
            <Button size="sm" onClick={() => setIsAddMediaOpen(true)} className="bg-sky-600 hover:bg-sky-700 text-white">
              <Plus className="h-4 w-4 mr-2" />
              Add Reel / Media
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {mediaList.length === 0 ? (
              <div className="col-span-full py-12 text-center text-slate-500 text-sm">
                No approved media registered yet. Click "Add Reel / Media" to link an Instagram Reel.
              </div>
            ) : (
              mediaList.map((m) => (
                <Card key={m.id} className="overflow-hidden">
                  <CardContent className="pt-4 pb-4 space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="font-semibold text-slate-900 text-sm">{m.title}</div>
                      <Badge variant={m.is_active ? 'success' : 'secondary'} className="text-[10px]">
                        {m.is_active ? 'Active' : 'Archived'}
                      </Badge>
                    </div>

                    {m.caption && <p className="text-xs text-slate-600 line-clamp-2">{m.caption}</p>}

                    {m.instagram_url && (
                      <a
                        href={m.instagram_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center text-xs text-sky-600 hover:underline gap-1"
                      >
                        <ExternalLink className="h-3 w-3" />
                        View Instagram Post
                      </a>
                    )}

                    {m.tags && m.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {m.tags.map((t, i) => (
                          <span key={i} className="text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                            #{t}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="pt-2 border-t flex items-center justify-between text-[11px] text-slate-400">
                      <span>Added {formatISTDateTime(m.created_at)}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteMedia(m.id)}
                        className="text-red-500 hover:text-red-700 text-xs h-6 px-2"
                      >
                        Delete
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 4: LEGACY CUTOVER */}
      {activeTab === 'migration' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <ArrowRightLeft className="h-5 w-5 text-indigo-600" />
                    YCloud & n8n Legacy Migration Cutover State Machine
                  </CardTitle>
                  <CardDescription>
                    Deterministic transition framework ensuring mutual exclusion between legacy n8n workflows and the new engine.
                  </CardDescription>
                </div>
                {isOwnerOrAdmin && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (migrationStatus) setSelectedCutoverState(migrationStatus.cutover_state);
                      setIsCutoverModalOpen(true);
                    }}
                    className="border-indigo-300 text-indigo-700 hover:bg-indigo-50"
                  >
                    Transition Cutover State
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Mutual Exclusion Warning */}
              <div className="p-4 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-950 flex items-start gap-3 text-xs">
                <ShieldCheck className="h-5 w-5 text-indigo-600 flex-shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <div className="font-semibold">Mutual Exclusion Invariant Enforced</div>
                  <p>
                    When cutover state is <span className="font-mono bg-indigo-100 px-1 rounded">legacy_active</span> or{' '}
                    <span className="font-mono bg-indigo-100 px-1 rounded">shadow_comparison</span>, all outbound campaign
                    dispatches in this system are strictly blocked to prevent sending duplicate messages alongside n8n.
                  </p>
                </div>
              </div>

              {/* State Overview */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-3 bg-slate-50 rounded border">
                  <span className="text-xs text-slate-500 block">Current Cutover State</span>
                  <Badge variant="outline" className="mt-1 font-mono uppercase text-xs">
                    {migrationStatus?.cutover_state || 'legacy_active'}
                  </Badge>
                </div>
                <div className="p-3 bg-slate-50 rounded border">
                  <span className="text-xs text-slate-500 block">Legacy System</span>
                  <span className="text-sm font-semibold text-slate-900 mt-1 block">
                    {migrationStatus?.legacy_system_name || 'Physio One n8n / YCloud'}
                  </span>
                </div>
                <div className="p-3 bg-slate-50 rounded border">
                  <span className="text-xs text-slate-500 block">Live Outbound Dispatch</span>
                  <span
                    className={`text-xs font-semibold mt-1 inline-flex items-center gap-1 ${
                      migrationStatus?.is_live_dispatch_blocked ? 'text-red-600' : 'text-emerald-600'
                    }`}
                  >
                    {migrationStatus?.is_live_dispatch_blocked ? (
                      <>
                        <XCircle className="h-3.5 w-3.5" /> Blocked (Mutual Exclusion)
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5" /> Active in New Engine
                      </>
                    )}
                  </span>
                </div>
                <div className="p-3 bg-slate-50 rounded border">
                  <span className="text-xs text-slate-500 block">Discrepancy History</span>
                  <span className="text-sm font-semibold text-slate-900 mt-1 block">
                    {migrationStatus?.dry_run_discrepancy_count || 0} items
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-3 pt-2">
                <Button onClick={handleRunDryRun} disabled={isDryRunning} className="bg-indigo-600 hover:bg-indigo-700 text-white">
                  <Play className={`h-4 w-4 mr-2 ${isDryRunning ? 'animate-spin' : ''}`} />
                  {isDryRunning ? 'Comparing Audiences...' : 'Run Dry-Run Comparison'}
                </Button>
                <span className="text-xs text-slate-500">
                  Last comparison: {formatISTDateTime(migrationStatus?.last_dry_run_at)}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* TAB 5: CSV IMPORT */}
      {activeTab === 'csv_import' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <FileSpreadsheet className="h-5 w-5 text-emerald-600" />
                Contact List CSV Import & Normalization
              </CardTitle>
              <CardDescription>
                Import contact batches with automatic E.164 phone normalization, deduplication, and spreadsheet formula injection protection.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-3 rounded-lg bg-slate-50 border text-xs text-slate-600 space-y-1">
                <p className="font-semibold text-slate-800">CSV Structure Guidelines:</p>
                <p>
                  Accepted columns: <span className="font-mono bg-slate-100 px-1 py-0.5 rounded">name, phone, marketing_consent</span>.
                  Phone numbers without country code will default to +91. Formula characters (<code>=, +, -, @</code>) in text fields are safely escaped with a leading quote.
                </p>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Paste CSV Content:</label>
                <textarea
                  rows={6}
                  value={csvText}
                  onChange={(e) => setCsvText(e.target.value)}
                  className="w-full text-xs font-mono p-3 border rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="flex items-center justify-between">
                <Button onClick={handleImportCsv} disabled={isImporting} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                  <Upload className={`h-4 w-4 mr-2 ${isImporting ? 'animate-spin' : ''}`} />
                  {isImporting ? 'Importing Batch...' : 'Import CSV Contacts'}
                </Button>
              </div>

              {/* Import Results Report */}
              {csvReport && (
                <div className="mt-4 p-4 border rounded-lg bg-emerald-50/50 space-y-3">
                  <div className="font-semibold text-emerald-900 text-sm flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    CSV Import Execution Summary
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
                    <div className="p-2 bg-white rounded border">
                      <span className="text-slate-500 block">Total Rows:</span>
                      <span className="font-bold text-slate-800">{csvReport.total_rows}</span>
                    </div>
                    <div className="p-2 bg-white rounded border">
                      <span className="text-slate-500 block">Accepted:</span>
                      <span className="font-bold text-emerald-600">{csvReport.accepted_count}</span>
                    </div>
                    <div className="p-2 bg-white rounded border">
                      <span className="text-slate-500 block">New Contacts:</span>
                      <span className="font-bold text-sky-600">{csvReport.created_contacts_count}</span>
                    </div>
                    <div className="p-2 bg-white rounded border">
                      <span className="text-slate-500 block">Duplicates Filtered:</span>
                      <span className="font-bold text-amber-600">{csvReport.duplicate_count}</span>
                    </div>
                    <div className="p-2 bg-white rounded border">
                      <span className="text-slate-500 block">Rejected:</span>
                      <span className="font-bold text-red-600">{csvReport.rejected_count}</span>
                    </div>
                  </div>

                  {csvReport.rejections.length > 0 && (
                    <div className="mt-2 text-xs">
                      <span className="font-semibold text-red-700 block mb-1">Rejection Details:</span>
                      <div className="space-y-1 max-h-32 overflow-y-auto">
                        {csvReport.rejections.map((rej, idx) => (
                          <div key={idx} className="p-1 bg-red-50 text-red-800 rounded border border-red-200">
                            Row {rej.row}: {rej.reason} {rej.phone ? `(${rej.phone})` : ''}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* CREATE CAMPAIGN MODAL */}
      <Dialog isOpen={isCreateOpen} onClose={() => setIsCreateOpen(false)} title="Create New Campaign">
        <form onSubmit={handleCreateCampaign} className="space-y-4 text-xs">
          <div>
            <label className="font-medium text-slate-700 block mb-1">Campaign Title *</label>
            <Input
              required
              placeholder="e.g. November Knee Pain Instagram Reel Re-engagement"
              value={campaignForm.title}
              onChange={(e) => setCampaignForm({ ...campaignForm, title: e.target.value })}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-medium text-slate-700 block mb-1">Campaign Type</label>
              <select
                value={campaignForm.campaign_type}
                onChange={(e) => setCampaignForm({ ...campaignForm, campaign_type: e.target.value })}
                className="w-full px-2.5 py-1.5 border rounded-md bg-white text-slate-800"
              >
                <option value="instagram_reengagement">Instagram Re-engagement</option>
                <option value="patient_education">Patient Education</option>
                <option value="seasonal_broadcast">Seasonal Broadcast</option>
                <option value="custom_broadcast">Custom Broadcast</option>
              </select>
            </div>
            <div>
              <label className="font-medium text-slate-700 block mb-1">Provider Adapter</label>
              <select
                value={campaignForm.provider}
                onChange={(e) => setCampaignForm({ ...campaignForm, provider: e.target.value })}
                className="w-full px-2.5 py-1.5 border rounded-md bg-white text-slate-800"
              >
                <option value="meta">Meta Cloud API</option>
                <option value="ycloud">YCloud</option>
              </select>
            </div>
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Select Media / Reel (Optional)</label>
            <select
              value={campaignForm.media_id}
              onChange={(e) => setCampaignForm({ ...campaignForm, media_id: e.target.value })}
              className="w-full px-2.5 py-1.5 border rounded-md bg-white text-slate-800"
            >
              <option value="">No media attachment</option>
              {mediaList.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title} ({m.instagram_url ? 'Instagram Reel' : m.media_type})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">WhatsApp Template Name</label>
            <Input
              placeholder="e.g. reengagement_reel_v1"
              value={campaignForm.template_name}
              onChange={(e) => setCampaignForm({ ...campaignForm, template_name: e.target.value })}
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Message Body / Fallback Copy</label>
            <textarea
              rows={3}
              value={campaignForm.custom_message_body}
              onChange={(e) => setCampaignForm({ ...campaignForm, custom_message_body: e.target.value })}
              className="w-full p-2 border rounded-md bg-white"
            />
          </div>

          {/* Targeting Rules */}
          <div className="p-3 bg-slate-50 rounded border space-y-2">
            <span className="font-semibold text-slate-800 block">Eligibility & Exclusion Gates</span>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-slate-600 block">Min Hours Elapsed (Default: 24)</label>
                <Input
                  type="number"
                  value={campaignForm.min_hours}
                  onChange={(e) => setCampaignForm({ ...campaignForm, min_hours: Number(e.target.value) })}
                />
              </div>
              <div>
                <label className="text-slate-600 block">Max Hours Elapsed (Default: 48)</label>
                <Input
                  type="number"
                  value={campaignForm.max_hours}
                  onChange={(e) => setCampaignForm({ ...campaignForm, max_hours: Number(e.target.value) })}
                />
              </div>
            </div>

            <div className="space-y-1 pt-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={campaignForm.require_marketing_consent}
                  onChange={(e) => setCampaignForm({ ...campaignForm, require_marketing_consent: e.target.checked })}
                  className="rounded text-emerald-600"
                />
                <span>Require explicit marketing consent</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={campaignForm.exclude_already_booked}
                  onChange={(e) => setCampaignForm({ ...campaignForm, exclude_already_booked: e.target.checked })}
                  className="rounded text-emerald-600"
                />
                <span>Exclude patients with active upcoming appointments</span>
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" className="bg-emerald-600 hover:bg-emerald-700 text-white">
              Create Campaign (Draft)
            </Button>
          </div>
        </form>
      </Dialog>

      {/* AUDIENCE PREVIEW MODAL */}
      <Dialog isOpen={isPreviewOpen} onClose={() => setIsPreviewOpen(false)} title="Audience & Template Preview">
        {previewData && (
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-3 gap-2">
              <div className="p-3 bg-slate-50 rounded border text-center">
                <span className="text-slate-500 block">Evaluated</span>
                <span className="text-lg font-bold text-slate-800">{previewData.total_evaluated}</span>
              </div>
              <div className="p-3 bg-emerald-50 rounded border border-emerald-200 text-center">
                <span className="text-emerald-700 block font-medium">Eligible</span>
                <span className="text-lg font-bold text-emerald-700">{previewData.eligible_count}</span>
              </div>
              <div className="p-3 bg-amber-50 rounded border border-amber-200 text-center">
                <span className="text-amber-700 block font-medium">Suppressed</span>
                <span className="text-lg font-bold text-amber-700">{previewData.suppressed_count}</span>
              </div>
            </div>

            {/* Suppression Breakdown */}
            {Object.keys(previewData.suppression_breakdown).length > 0 && (
              <div className="p-3 bg-slate-50 rounded border space-y-1">
                <span className="font-semibold text-slate-800 block">Suppression Breakdown:</span>
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {Object.entries(previewData.suppression_breakdown).map(([reason, count]) => (
                    <span key={reason} className="bg-white px-2 py-0.5 rounded border text-[11px] text-slate-700">
                      {reason.replace('_', ' ')}: <strong>{count}</strong>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Sample Rendered Message */}
            {previewData.sample_rendered_message && (
              <div>
                <span className="font-semibold text-slate-800 block mb-1">Sample Rendered Message:</span>
                <div className="p-3 bg-slate-100 rounded font-mono text-slate-800 border">
                  {previewData.sample_rendered_message}
                </div>
              </div>
            )}

            {/* Sample Eligible Recipients */}
            <div>
              <span className="font-semibold text-slate-800 block mb-1">
                Sample Eligible Recipients ({previewData.sample_eligible_recipients.length}):
              </span>
              <div className="max-h-40 overflow-y-auto border rounded divide-y">
                {previewData.sample_eligible_recipients.map((r, i) => (
                  <div key={i} className="p-2 flex items-center justify-between bg-white text-[11px]">
                    <div>
                      <span className="font-medium text-slate-800">{r.name || 'Patient'}</span>
                      <span className="text-slate-400 ml-2">+{r.wa_id}</span>
                    </div>
                    <span className="text-slate-500">Active: {formatISTDateTime(r.last_active_at)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-between items-center pt-2 border-t">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (activeCampaign) handlePreviewAudience(activeCampaign, true);
                }}
              >
                Save Audience List to Campaign
              </Button>
              <Button size="sm" onClick={() => setIsPreviewOpen(false)}>
                Close Preview
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* APPROVAL DECISION DIALOG */}
      <Dialog isOpen={isApprovalDialogOpen} onClose={() => setIsApprovalDialogOpen(false)} title="Campaign Authorization Review">
        {selectedCampaignForApproval && (
          <div className="space-y-4 text-xs">
            <p>
              You are about to <strong className="uppercase">{approvalDecision}</strong> campaign{' '}
              <strong>"{selectedCampaignForApproval.title}"</strong> (Snapshot v{selectedCampaignForApproval.current_version}).
            </p>

            <div>
              <label className="font-semibold text-slate-700 block mb-1">
                Review Notes {approvalDecision === 'reject' && '* (Required for rejection)'}
              </label>
              <textarea
                rows={3}
                required={approvalDecision === 'reject'}
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                placeholder="Audit notes, reason for decision, or verification details..."
                className="w-full p-2 border rounded-md"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" size="sm" onClick={() => setIsApprovalDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleApprovalAction}
                className={
                  approvalDecision === 'approve'
                    ? 'bg-purple-600 hover:bg-purple-700 text-white'
                    : 'bg-red-600 hover:bg-red-700 text-white'
                }
              >
                Confirm {approvalDecision === 'approve' ? 'Approval' : 'Rejection'}
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* ANALYTICS MODAL */}
      <Dialog isOpen={isAnalyticsOpen} onClose={() => setIsAnalyticsOpen(false)} title="Campaign Delivery & Attribution Analytics">
        {analyticsData && (
          <div className="space-y-4 text-xs">
            {/* KPI Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="p-2.5 bg-slate-50 rounded border text-center">
                <span className="text-slate-500 block text-[11px]">Delivery Rate</span>
                <span className="text-base font-bold text-emerald-600">{analyticsData.delivery_rate_pct}%</span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded border text-center">
                <span className="text-slate-500 block text-[11px]">Read Rate</span>
                <span className="text-base font-bold text-sky-600">{analyticsData.read_rate_pct}%</span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded border text-center">
                <span className="text-slate-500 block text-[11px]">Conversion Rate (72h)</span>
                <span className="text-base font-bold text-indigo-600">{analyticsData.conversion_rate_pct}%</span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded border text-center">
                <span className="text-slate-500 block text-[11px]">Failure Rate</span>
                <span className="text-base font-bold text-red-600">{analyticsData.failure_rate_pct}%</span>
              </div>
            </div>

            {/* Attribution Window Notice */}
            <div className="p-2.5 bg-indigo-50 border border-indigo-200 rounded text-indigo-900 text-[11px]">
              Attribution Window: <strong>72 hours</strong>. Confirmed clinic appointments created within 72 hours of message delivery are attributed directly to this campaign.
            </div>

            {/* Recipients Sample Table */}
            <div>
              <span className="font-semibold text-slate-800 block mb-1">
                Recent Recipients ({analyticsRecipients.length}):
              </span>
              <div className="max-h-48 overflow-y-auto border rounded divide-y">
                {analyticsRecipients.map((r) => (
                  <div key={r.id} className="p-2 flex items-center justify-between bg-white text-[11px]">
                    <div>
                      <span className="font-medium text-slate-800">{r.contact_name || 'Patient'}</span>
                      <span className="text-slate-400 ml-2">{r.phone_e164}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          r.status === 'delivered' || r.status === 'read'
                            ? 'success'
                            : r.status === 'converted'
                            ? 'default'
                            : r.status === 'failed'
                            ? 'destructive'
                            : 'secondary'
                        }
                        className="text-[10px] capitalize"
                      >
                        {r.status}
                      </Badge>
                      {r.converted_at && <span className="text-indigo-600 font-semibold">Converted</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t">
              <Button size="sm" onClick={() => setIsAnalyticsOpen(false)}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* ADD REEL MEDIA MODAL */}
      <Dialog isOpen={isAddMediaOpen} onClose={() => setIsAddMediaOpen(false)} title="Add Instagram Reel or Media">
        <form onSubmit={handleAddMedia} className="space-y-4 text-xs">
          <div>
            <label className="font-medium text-slate-700 block mb-1">Media / Reel Title *</label>
            <Input
              required
              placeholder="e.g. Post-Run Hamstring Mobility Protocol"
              value={mediaForm.title}
              onChange={(e) => setMediaForm({ ...mediaForm, title: e.target.value })}
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Instagram Reel URL *</label>
            <Input
              required
              placeholder="https://www.instagram.com/reel/Cxxxxxx/"
              value={mediaForm.instagram_url}
              onChange={(e) => setMediaForm({ ...mediaForm, instagram_url: e.target.value })}
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Caption / Notes</label>
            <textarea
              rows={2}
              placeholder="Brief summary of therapeutic exercises shown in this reel..."
              value={mediaForm.caption}
              onChange={(e) => setMediaForm({ ...mediaForm, caption: e.target.value })}
              className="w-full p-2 border rounded-md"
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Tags (Comma-separated)</label>
            <Input
              placeholder="kneepain, hamstring, mobility, runners"
              value={mediaForm.tags}
              onChange={(e) => setMediaForm({ ...mediaForm, tags: e.target.value })}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button type="button" variant="outline" size="sm" onClick={() => setIsAddMediaOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" className="bg-sky-600 hover:bg-sky-700 text-white">
              Save to Library
            </Button>
          </div>
        </form>
      </Dialog>

      {/* DRY RUN COMPARISON MODAL */}
      <Dialog isOpen={isDryRunOpen} onClose={() => setIsDryRunOpen(false)} title="n8n vs New Engine Dry-Run Comparison">
        {dryRunData && (
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-4 gap-2 text-center">
              <div className="p-2 bg-slate-50 rounded border">
                <span className="text-slate-500 block text-[10px]">Evaluated</span>
                <span className="text-sm font-bold">{dryRunData.total_evaluated}</span>
              </div>
              <div className="p-2 bg-slate-50 rounded border">
                <span className="text-slate-500 block text-[10px]">Legacy Eligible</span>
                <span className="text-sm font-bold">{dryRunData.legacy_predicted_count}</span>
              </div>
              <div className="p-2 bg-emerald-50 rounded border border-emerald-200">
                <span className="text-emerald-700 block text-[10px]">New Eligible</span>
                <span className="text-sm font-bold text-emerald-700">{dryRunData.new_engine_eligible_count}</span>
              </div>
              <div className="p-2 bg-amber-50 rounded border border-amber-200">
                <span className="text-amber-700 block text-[10px]">Discrepancies</span>
                <span className="text-sm font-bold text-amber-700">{dryRunData.discrepancy_count}</span>
              </div>
            </div>

            {dryRunData.discrepancies.length > 0 ? (
              <div className="border rounded divide-y max-h-48 overflow-y-auto">
                {dryRunData.discrepancies.map((d, i) => (
                  <div key={i} className="p-2 flex items-center justify-between text-[11px] bg-white">
                    <div>
                      <span className="font-mono text-slate-800">+{d.wa_id}</span>
                      <span className="text-slate-500 ml-2">Reason: {d.reason}</span>
                    </div>
                    <div className="flex gap-2 text-[10px]">
                      <span className="bg-slate-100 px-1.5 py-0.5 rounded">Legacy: {d.legacy_status}</span>
                      <span className="bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">New: {d.new_engine_status}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 bg-emerald-50 text-emerald-800 rounded border border-emerald-200 text-center">
                100% targeting match. No discrepancies found between legacy n8n rules and new engine logic.
              </div>
            )}

            <div className="flex justify-end pt-2 border-t">
              <Button size="sm" onClick={() => setIsDryRunOpen(false)}>
                Close
              </Button>
            </div>
          </div>
        )}
      </Dialog>

      {/* CUTOVER STATE TRANSITION MODAL */}
      <Dialog isOpen={isCutoverModalOpen} onClose={() => setIsCutoverModalOpen(false)} title="Transition Cutover State">
        <div className="space-y-4 text-xs">
          <div>
            <label className="font-semibold text-slate-700 block mb-1">Target Cutover State</label>
            <select
              value={selectedCutoverState}
              onChange={(e) => setSelectedCutoverState(e.target.value)}
              className="w-full p-2 border rounded-md bg-white text-slate-800"
            >
              <option value="legacy_active">legacy_active (n8n sends, new engine blocked)</option>
              <option value="shadow_comparison">shadow_comparison (Dry-run audits only, live dispatch blocked)</option>
              <option value="migration_ready">migration_ready (Audits verified, ready for final switch)</option>
              <option value="new_active">new_active (New engine sends WhatsApp campaigns, n8n disabled)</option>
              <option value="rolled_back">rolled_back (Rollback to legacy n8n)</option>
            </select>
          </div>

          <div>
            <label className="font-semibold text-slate-700 block mb-1">Transition Audit Notes</label>
            <textarea
              rows={2}
              value={cutoverNotes}
              onChange={(e) => setCutoverNotes(e.target.value)}
              placeholder="e.g. Completed dry-run audit with 0 discrepancies. Staff sign-off approved."
              className="w-full p-2 border rounded-md"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button variant="outline" size="sm" onClick={() => setIsCutoverModalOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSetCutoverState} className="bg-indigo-600 hover:bg-indigo-700 text-white">
              Apply Transition
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
