'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import {
  api,
  AutomationRule,
  AutomationScheduledJob,
  AutomationMessageTemplate,
  AutomationExecutionLog,
  AutomationSuppressionLog,
  AutomationSettings,
} from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Dialog } from '@/components/ui/dialog';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/table';
import {
  Clock,
  Calendar,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Plus,
  Play,
  Pause,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  FileText,
  Search,
  Filter,
  Eye,
  Send,
  Zap,
  Info,
  Sliders,
  Settings as SettingsIcon,
  ChevronRight,
  ListFilter,
  Check,
  X,
} from 'lucide-react';

// Format UTC/ISO timestamp to IST (Asia/Kolkata) display
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

export default function AutomationsPage() {
  const { user, role } = useAuth();
  const isAdminOrOwner = role === 'Owner' || role === 'Admin';
  const isOperator = role === 'Operator';
  const canManage = isAdminOrOwner || isOperator;

  // Active Tab
  const [activeTab, setActiveTab] = useState<'rules' | 'jobs' | 'templates' | 'executions' | 'settings'>('rules');

  // Loading & Error States
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Data States
  const [settings, setSettings] = useState<AutomationSettings | null>(null);
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [jobs, setJobs] = useState<AutomationScheduledJob[]>([]);
  const [totalJobs, setTotalJobs] = useState<number>(0);
  const [templates, setTemplates] = useState<AutomationMessageTemplate[]>([]);
  const [executions, setExecutions] = useState<AutomationExecutionLog[]>([]);
  const [suppressions, setSuppressions] = useState<AutomationSuppressionLog[]>([]);

  // Filter States
  const [jobStatusFilter, setJobStatusFilter] = useState<string>('all');
  const [jobSearchPhone, setJobSearchPhone] = useState<string>('');
  const [logTypeFilter, setLogTypeFilter] = useState<'executions' | 'suppressions'>('executions');

  // Modal States
  const [showKillSwitchConfirm, setShowKillSwitchConfirm] = useState<boolean>(false);
  const [pendingKillSwitchValue, setPendingKillSwitchValue] = useState<boolean>(false);
  const [selectedJob, setSelectedJob] = useState<AutomationScheduledJob | null>(null);
  const [showJobModal, setShowJobModal] = useState<boolean>(false);
  const [selectedTemplate, setSelectedTemplate] = useState<AutomationMessageTemplate | null>(null);
  const [showTemplateModal, setShowTemplateModal] = useState<boolean>(false);
  const [showCreateFollowupModal, setShowCreateFollowupModal] = useState<boolean>(false);
  const [showWorkerResultModal, setShowWorkerResultModal] = useState<boolean>(false);
  const [workerResult, setWorkerResult] = useState<Record<string, unknown> | null>(null);

  // New Follow-up Form
  const [newFollowupContactId, setNewFollowupContactId] = useState<string>('');
  const [newFollowupScheduledFor, setNewFollowupScheduledFor] = useState<string>('');
  const [newFollowupReason, setNewFollowupReason] = useState<string>('Staff check-in');
  const [newFollowupMessage, setNewFollowupMessage] = useState<string>('');

  // Fetch Core Data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [settingsRes, rulesRes, jobsRes, templatesRes] = await Promise.all([
        api.getAutomationSettings().catch(() => null),
        api.getAutomationRules().catch(() => ({ items: [], total: 0 })),
        api.getScheduledJobs({ limit: 50 }).catch(() => ({ items: [], total: 0 })),
        api.getAutomationTemplates().catch(() => ({ items: [], total: 0 })),
      ]);

      if (settingsRes) setSettings(settingsRes);
      if (rulesRes) setRules(rulesRes.items);
      if (jobsRes) {
        setJobs(jobsRes.items);
        setTotalJobs(jobsRes.total);
      }
      if (templatesRes) setTemplates(templatesRes.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load automation data.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch Logs on Tab Change
  const fetchLogs = useCallback(async () => {
    try {
      if (logTypeFilter === 'executions') {
        const res = await api.getAutomationExecutions({ limit: 50 });
        setExecutions(res.items);
      } else {
        const res = await api.getAutomationSuppressions({ limit: 50 });
        setSuppressions(res.items);
      }
    } catch (err: unknown) {
      console.error('Failed to load logs:', err);
    }
  }, [logTypeFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (activeTab === 'executions') {
      fetchLogs();
    }
  }, [activeTab, logTypeFilter, fetchLogs]);

  // Handle Kill Switch Toggle
  const handleToggleKillSwitch = async () => {
    if (!isAdminOrOwner || !settings) return;
    setActionLoading(true);
    setError(null);
    try {
      const updated = await api.updateAutomationSettings({
        outbound_enabled: pendingKillSwitchValue,
      });
      setSettings(updated);
      setSuccessMessage(
        updated.outbound_enabled
          ? 'Global automation outbound has been ACTIVATED.'
          : 'Global automation outbound has been DISABLED (Kill Switch active).'
      );
      setShowKillSwitchConfirm(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update outbound kill switch.');
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Rule Enable/Disable
  const handleToggleRule = async (rule: AutomationRule) => {
    if (!canManage) return;
    setActionLoading(true);
    setError(null);
    try {
      if (rule.is_enabled) {
        await api.disableAutomationRule(rule.id);
        setSuccessMessage(`Rule "${rule.name}" disabled.`);
      } else {
        await api.enableAutomationRule(rule.id);
        setSuccessMessage(`Rule "${rule.name}" enabled.`);
      }
      const refreshed = await api.getAutomationRules();
      setRules(refreshed.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to toggle rule state.');
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Job Cancel
  const handleCancelJob = async (jobId: string) => {
    if (!canManage) return;
    if (!confirm('Are you sure you want to cancel this scheduled job?')) return;
    setActionLoading(true);
    try {
      await api.cancelScheduledJob(jobId, 'Cancelled via Automations Dashboard');
      setSuccessMessage('Scheduled job cancelled.');
      const res = await api.getScheduledJobs({ limit: 50 });
      setJobs(res.items);
      setTotalJobs(res.total);
      if (selectedJob && selectedJob.id === jobId) {
        setShowJobModal(false);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel job.');
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Job Retry
  const handleRetryJob = async (jobId: string) => {
    if (!canManage) return;
    setActionLoading(true);
    try {
      await api.retryScheduledJob(jobId, true);
      setSuccessMessage('Job reset to scheduled status for immediate retry.');
      const res = await api.getScheduledJobs({ limit: 50 });
      setJobs(res.items);
      setTotalJobs(res.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to retry job.');
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Create Staff Followup
  const handleCreateStaffFollowup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canManage) return;
    if (!newFollowupContactId || !newFollowupScheduledFor) {
      setError('Contact ID and Scheduled Send Time are required.');
      return;
    }

    setActionLoading(true);
    setError(null);
    try {
      await api.createStaffScheduledJob({
        contact_id: newFollowupContactId,
        scheduled_for: new Date(newFollowupScheduledFor).toISOString(),
        reason: newFollowupReason,
        message_text: newFollowupMessage || undefined,
      });
      setSuccessMessage('Patient follow-up scheduled successfully.');
      setShowCreateFollowupModal(false);
      setNewFollowupContactId('');
      setNewFollowupScheduledFor('');
      setNewFollowupMessage('');
      const res = await api.getScheduledJobs({ limit: 50 });
      setJobs(res.items);
      setTotalJobs(res.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create staff follow-up.');
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Manual Worker Cycle Trigger
  const handleTriggerWorker = async () => {
    if (!canManage) return;
    setActionLoading(true);
    setError(null);
    try {
      const result = await api.triggerAutomationWorker(20);
      setWorkerResult(result);
      setShowWorkerResultModal(true);
      setSuccessMessage(`Worker cycle executed: ${result.sent_count} sent, ${result.suppressed_count} suppressed, ${result.failed_count} failed.`);
      fetchData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to trigger worker cycle.');
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Inactivity Scan Trigger
  const handleTriggerInactivityScan = async () => {
    if (!canManage) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await api.triggerInactivityScan();
      setSuccessMessage(`Inactivity scan complete: ${res.newly_scheduled_count} new follow-up jobs scheduled.`);
      fetchData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to run inactivity scan.');
    } finally {
      setActionLoading(false);
    }
  };

  // Filtered Jobs
  const filteredJobs = jobs.filter((job) => {
    if (jobStatusFilter !== 'all' && job.status !== jobStatusFilter) return false;
    if (jobSearchPhone) {
      const phone = job.contact_phone || '';
      const name = job.contact_name || '';
      const term = jobSearchPhone.toLowerCase();
      if (!phone.includes(term) && !name.toLowerCase().includes(term)) return false;
    }
    return true;
  });

  // Derived counts for overview
  const activeRulesCount = rules.filter((r) => r.is_enabled).length;
  const queuedJobsCount = jobs.filter((j) => ['scheduled', 'queued', 'eligible', 'sending'].includes(j.status)).length;
  const failedJobsCount = jobs.filter((j) => ['failed', 'dead_letter'].includes(j.status)).length;
  const suppressedJobsCount = jobs.filter((j) => j.status === 'suppressed').length;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <Clock className="h-7 w-7 text-teal-600" />
            Automations & Scheduled Messaging
          </h1>
          <p className="text-sm text-slate-500">
            Durable PostgreSQL scheduling, appointment reminders, patient follow-up automation, and worker leases.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchData}
            disabled={loading || actionLoading}
            className="flex items-center gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          {canManage && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowCreateFollowupModal(true)}
              className="bg-teal-600 hover:bg-teal-700 text-white flex items-center gap-1.5"
            >
              <Plus className="h-4 w-4" />
              Schedule Follow-up
            </Button>
          )}
        </div>
      </div>

      {/* Global Outbound Kill Switch Banner */}
      <div
        className={`rounded-lg border p-4 transition-colors ${
          settings?.outbound_enabled
            ? 'bg-emerald-50 border-emerald-200 text-emerald-950'
            : 'bg-amber-50 border-amber-300 text-amber-950'
        }`}
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5">
              {settings?.outbound_enabled ? (
                <ShieldCheck className="h-6 w-6 text-emerald-600" />
              ) : (
                <ShieldAlert className="h-6 w-6 text-amber-600" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-base">
                  {settings?.outbound_enabled
                    ? 'Automated Outbound Dispatch: ACTIVE'
                    : 'Automated Outbound Dispatch: DISABLED (Kill Switch Engaged)'}
                </span>
                <Badge
                  variant={settings?.outbound_enabled ? 'default' : 'destructive'}
                  className={settings?.outbound_enabled ? 'bg-emerald-600' : 'bg-amber-600'}
                >
                  {settings?.outbound_enabled ? 'ENABLED' : 'MUTED'}
                </Badge>
              </div>
              <p className="text-xs text-slate-600 mt-1">
                {settings?.outbound_enabled
                  ? 'Scheduled reminders and follow-ups are being actively dispatched to WhatsApp during permitted hours.'
                  : 'All automated WhatsApp dispatch is suppressed at the safety gate. Jobs remain queued or suppressed until outbound is activated.'}
                {' Timezone: '}
                <span className="font-mono font-medium text-slate-800">
                  {settings?.default_timezone || 'Asia/Kolkata'}
                </span>
                {' | Quiet Hours: '}
                <span className="font-mono font-medium text-slate-800">
                  {settings?.quiet_hours_start || '21:00'} - {settings?.quiet_hours_end || '09:00'} IST
                </span>
              </p>
            </div>
          </div>
          {isAdminOrOwner && (
            <Button
              variant={settings?.outbound_enabled ? 'destructive' : 'primary'}
              size="sm"
              onClick={() => {
                setPendingKillSwitchValue(!settings?.outbound_enabled);
                setShowKillSwitchConfirm(true);
              }}
              disabled={actionLoading}
              className={
                !settings?.outbound_enabled
                  ? 'bg-emerald-700 hover:bg-emerald-800 text-white'
                  : ''
              }
            >
              {settings?.outbound_enabled ? 'Engage Kill Switch (Disable)' : 'Activate Outbound Dispatch'}
            </Button>
          )}
        </div>
      </div>

      {/* Alert Banners */}
      {error && (
        <Alert variant="destructive" title="Automation Error">
          {error}
        </Alert>
      )}
      {successMessage && (
        <Alert variant="success" title="Success">
          {successMessage}
        </Alert>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">Active Rules</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-slate-900">
                {activeRulesCount} <span className="text-sm font-normal text-slate-400">/ {rules.length}</span>
              </span>
              <Badge variant={activeRulesCount > 0 ? 'default' : 'secondary'} className="text-xs">
                {activeRulesCount > 0 ? 'Operating' : 'All Disabled'}
              </Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">Pending / Queued Jobs</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-teal-600">{queuedJobsCount}</span>
              <Clock className="h-4 w-4 text-slate-400" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">Suppressed (Safety Gate)</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className="text-2xl font-bold text-amber-600">{suppressedJobsCount}</span>
              <ShieldAlert className="h-4 w-4 text-amber-400" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">Failed / Dead-letter</div>
            <div className="mt-1 flex items-baseline justify-between">
              <span className={`text-2xl font-bold ${failedJobsCount > 0 ? 'text-red-600' : 'text-slate-900'}`}>
                {failedJobsCount}
              </span>
              <AlertTriangle className={`h-4 w-4 ${failedJobsCount > 0 ? 'text-red-500' : 'text-slate-400'}`} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-6">
          <button
            onClick={() => setActiveTab('rules')}
            className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'rules'
                ? 'border-teal-600 text-teal-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Sliders className="h-4 w-4" />
            Automation Rules ({rules.length})
          </button>
          <button
            onClick={() => setActiveTab('jobs')}
            className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'jobs'
                ? 'border-teal-600 text-teal-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <Clock className="h-4 w-4" />
            Scheduled Jobs ({totalJobs})
          </button>
          <button
            onClick={() => setActiveTab('templates')}
            className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'templates'
                ? 'border-teal-600 text-teal-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <FileText className="h-4 w-4" />
            WhatsApp Templates ({templates.length})
          </button>
          <button
            onClick={() => setActiveTab('executions')}
            className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'executions'
                ? 'border-teal-600 text-teal-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <ListFilter className="h-4 w-4" />
            Logs & Suppressions
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`py-3 px-1 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'settings'
                ? 'border-teal-600 text-teal-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            <SettingsIcon className="h-4 w-4" />
            Worker & Settings
          </button>
        </nav>
      </div>

      {/* TAB 1: RULES */}
      {activeTab === 'rules' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Automation Rule Registry</h2>
            <div className="text-xs text-slate-500">
              Default rule policy: All new automations are seeded <span className="font-semibold text-amber-700">DISABLED</span> until explicitly authorized.
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {rules.map((rule) => {
              const isReminder = rule.automation_type === 'appointment_reminder';
              const isInactivity = rule.automation_type === 'inactivity_followup';
              const isFollowup = rule.automation_type === 'appointment_followup';
              const isNoShow = rule.automation_type === 'missed_appointment_followup';

              let offsetBadge = '';
              if (isReminder) {
                const hours = Math.round(rule.delay_minutes / 60);
                offsetBadge = `${hours}h Before Appointment`;
              } else if (isInactivity) {
                const hours = Math.round(rule.delay_minutes / 60);
                offsetBadge = `${hours}h Inactivity Trigger`;
              } else if (isFollowup) {
                const hours = Math.round(rule.delay_minutes / 60);
                offsetBadge = `${hours}h Post-Appointment`;
              } else if (isNoShow) {
                offsetBadge = 'On Authoritative No-Show';
              }

              return (
                <Card
                  key={rule.id}
                  className={`border transition-shadow hover:shadow-sm ${
                    rule.is_enabled ? 'border-teal-300 bg-white' : 'border-slate-200 bg-slate-50/60'
                  }`}
                >
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <CardTitle className="text-base font-bold text-slate-900">{rule.name}</CardTitle>
                          <Badge variant={rule.is_enabled ? 'default' : 'secondary'} className="text-xs">
                            {rule.is_enabled ? 'ENABLED' : 'DISABLED'}
                          </Badge>
                        </div>
                        <CardDescription className="text-xs mt-1">
                          Type: <span className="font-mono text-slate-700">{rule.automation_type}</span>
                        </CardDescription>
                      </div>
                      {canManage && (
                        <Button
                          size="sm"
                          variant={rule.is_enabled ? 'outline' : 'primary'}
                          onClick={() => handleToggleRule(rule)}
                          disabled={actionLoading}
                          className={!rule.is_enabled ? 'bg-teal-600 hover:bg-teal-700 text-white' : ''}
                        >
                          {rule.is_enabled ? (
                            <>
                              <Pause className="h-3.5 w-3.5 mr-1 text-slate-500" /> Disable
                            </>
                          ) : (
                            <>
                              <Play className="h-3.5 w-3.5 mr-1" /> Enable
                            </>
                          )}
                        </Button>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 pt-0 text-xs text-slate-600">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                        {offsetBadge || `${rule.delay_minutes}m delay`}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        Window: {rule.start_hour} - {rule.end_hour} IST
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        Cooldown: {rule.cooldown_hours}h
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                        Max Sends: {rule.max_sends_per_contact}
                      </span>
                    </div>

                    <div className="bg-slate-50 p-2.5 rounded border border-slate-200">
                      <div className="font-medium text-slate-700 mb-1">Assigned Template / Message:</div>
                      <div className="font-mono text-slate-800 text-[11px] truncate">
                        {rule.template_name ? `Template: ${rule.template_name}` : rule.fallback_body || 'No fallback message configured'}
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400">
                      <span>Provider: {rule.provider.toUpperCase()}</span>
                      <span>Updated: {formatISTDateTime(rule.updated_at)}</span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 2: SCHEDULED JOBS */}
      {activeTab === 'jobs' && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <Card>
            <CardContent className="pt-4 pb-4">
              <div className="flex flex-col sm:flex-row items-center gap-3">
                <div className="relative flex-1 w-full">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
                  <Input
                    placeholder="Search by patient phone or name..."
                    value={jobSearchPhone}
                    onChange={(e) => setJobSearchPhone(e.target.value)}
                    className="pl-9 h-9"
                  />
                </div>
                <div className="flex items-center gap-2 w-full sm:w-auto">
                  <span className="text-xs text-slate-500 whitespace-nowrap">Status:</span>
                  <select
                    value={jobStatusFilter}
                    onChange={(e) => setJobStatusFilter(e.target.value)}
                    className="h-9 text-xs rounded-md border border-slate-300 bg-white px-2.5 py-1 text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-500"
                  >
                    <option value="all">All Statuses ({totalJobs})</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="queued">Queued</option>
                    <option value="sending">Sending</option>
                    <option value="sent">Sent</option>
                    <option value="delivered">Delivered</option>
                    <option value="suppressed">Suppressed</option>
                    <option value="failed">Failed</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Jobs Table */}
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Recipient</TableHead>
                  <TableHead>Automation Type / Rule</TableHead>
                  <TableHead>Scheduled For (IST)</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Attempts</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredJobs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-slate-400">
                      No scheduled jobs matching the filter criteria.
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredJobs.map((job) => {
                    let statusColor = 'bg-slate-100 text-slate-700';

                    if (job.status === 'sent' || job.status === 'delivered') {
                      statusColor = 'bg-emerald-100 text-emerald-800';
                    } else if (job.status === 'scheduled' || job.status === 'queued') {
                      statusColor = 'bg-teal-100 text-teal-800';
                    } else if (job.status === 'suppressed') {
                      statusColor = 'bg-amber-100 text-amber-800';
                    } else if (job.status === 'failed' || job.status === 'dead_letter') {
                      statusColor = 'bg-red-100 text-red-800';
                    }

                    return (
                      <TableRow key={job.id}>
                        <TableCell>
                          <div className="font-medium text-slate-900">{job.contact_name || 'Patient'}</div>
                          <div className="font-mono text-xs text-slate-500">{job.contact_phone || job.contact_id}</div>
                        </TableCell>
                        <TableCell>
                          <div className="text-xs font-semibold text-slate-800">
                            {job.rule_name || job.automation_type}
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono">{job.automation_type}</div>
                        </TableCell>
                        <TableCell>
                          <div className="text-xs font-medium text-slate-800">
                            {formatISTDateTime(job.scheduled_for)}
                          </div>
                          {job.completed_at && (
                            <div className="text-[10px] text-slate-400">
                              Completed: {formatISTDateTime(job.completed_at)}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColor}`}>
                            {job.status}
                          </span>
                          {job.suppression_reason && (
                            <div className="text-[10px] text-amber-600 truncate max-w-[150px] mt-0.5" title={job.suppression_reason}>
                              {job.suppression_reason}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-slate-600 font-mono">
                            {job.attempt_count} / {job.max_attempts}
                          </span>
                        </TableCell>
                        <TableCell className="text-right space-x-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedJob(job);
                              setShowJobModal(true);
                            }}
                            className="h-8 px-2"
                            title="View Job Payload and Audit Details"
                          >
                            <Eye className="h-3.5 w-3.5 text-slate-600" />
                          </Button>
                          {canManage && (job.status === 'failed' || job.status === 'suppressed') && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleRetryJob(job.id)}
                              disabled={actionLoading}
                              className="h-8 px-2 text-teal-600 border-teal-200 hover:bg-teal-50"
                              title="Reset and Retry Immediately"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          {canManage && ['scheduled', 'queued', 'eligible'].includes(job.status) && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleCancelJob(job.id)}
                              disabled={actionLoading}
                              className="h-8 px-2 text-red-600 border-red-200 hover:bg-red-50"
                              title="Cancel Job"
                            >
                              <X className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}

      {/* TAB 3: MESSAGE TEMPLATES */}
      {activeTab === 'templates' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">WhatsApp HSM & Utility Message Templates</h2>
              <p className="text-xs text-slate-500">
                Pre-approved templates for WhatsApp 24-hour service window compliance. Outside 24h, only approved utility/marketing templates can be sent.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {templates.map((tmpl) => (
              <Card key={tmpl.id} className="border border-slate-200">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base font-bold text-slate-900">{tmpl.name}</CardTitle>
                        <Badge
                          variant={tmpl.approval_status === 'APPROVED' ? 'default' : 'secondary'}
                          className={tmpl.approval_status === 'APPROVED' ? 'bg-emerald-600 text-white' : 'bg-amber-100 text-amber-800'}
                        >
                          {tmpl.approval_status}
                        </Badge>
                      </div>
                      <CardDescription className="text-xs mt-1">
                        Category: <span className="font-semibold text-slate-700">{tmpl.category}</span> | Language: {tmpl.language} | Provider: {tmpl.provider.toUpperCase()}
                      </CardDescription>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setSelectedTemplate(tmpl);
                        setShowTemplateModal(true);
                      }}
                    >
                      <Eye className="h-4 w-4 text-slate-500" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 pt-0 text-xs">
                  <div className="bg-slate-50 p-3 rounded border border-slate-200 font-sans text-slate-800 text-xs leading-relaxed">
                    {tmpl.body}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-slate-400 font-medium mr-1 text-[11px]">Variables:</span>
                    {tmpl.variables.length === 0 ? (
                      <span className="text-slate-400 italic">None</span>
                    ) : (
                      tmpl.variables.map((v) => (
                        <span key={v} className="bg-teal-50 text-teal-700 border border-teal-200 px-1.5 py-0.5 rounded text-[10px] font-mono">
                          {`{{${v}}}`}
                        </span>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* TAB 4: LOGS & SUPPRESSIONS */}
      {activeTab === 'executions' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant={logTypeFilter === 'executions' ? 'primary' : 'outline'}
                onClick={() => setLogTypeFilter('executions')}
                className={logTypeFilter === 'executions' ? 'bg-teal-600 hover:bg-teal-700 text-white' : ''}
              >
                Execution Logs ({executions.length})
              </Button>
              <Button
                size="sm"
                variant={logTypeFilter === 'suppressions' ? 'primary' : 'outline'}
                onClick={() => setLogTypeFilter('suppressions')}
                className={logTypeFilter === 'suppressions' ? 'bg-amber-600 hover:bg-amber-700 text-white' : ''}
              >
                Suppression Logs ({suppressions.length})
              </Button>
            </div>
            <Button variant="ghost" size="sm" onClick={fetchLogs} className="text-xs">
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Reload Logs
            </Button>
          </div>

          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Timestamp (IST)</TableHead>
                  <TableHead>Contact / Job</TableHead>
                  <TableHead>{logTypeFilter === 'executions' ? 'Action / Transition' : 'Suppression Reason'}</TableHead>
                  <TableHead>Details / Payload</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logTypeFilter === 'executions' ? (
                  executions.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-center py-8 text-slate-400">
                        No execution logs recorded yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    executions.map((log) => (
                      <TableRow key={log.id}>
                        <TableCell className="text-xs font-mono text-slate-600 whitespace-nowrap">
                          {formatISTDateTime(log.created_at)}
                        </TableCell>
                        <TableCell>
                          <div className="text-xs font-medium text-slate-800">{log.automation_type}</div>
                          <div className="text-[10px] text-slate-400 font-mono">Job: {log.job_id.slice(0, 8)}...</div>
                        </TableCell>
                        <TableCell>
                          <div className="text-xs font-semibold text-slate-900">{log.action}</div>
                          {log.status_before && log.status_after && (
                            <div className="text-[11px] text-slate-500 font-mono">
                              {log.status_before} → {log.status_after}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <pre className="text-[10px] bg-slate-50 p-1.5 rounded max-w-sm truncate text-slate-700 font-mono">
                            {JSON.stringify(log.details)}
                          </pre>
                        </TableCell>
                      </TableRow>
                    ))
                  )
                ) : suppressions.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center py-8 text-slate-400">
                      No suppression logs recorded yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  suppressions.map((sup) => (
                    <TableRow key={sup.id}>
                      <TableCell className="text-xs font-mono text-slate-600 whitespace-nowrap">
                        {formatISTDateTime(sup.created_at)}
                      </TableCell>
                      <TableCell>
                        <div className="text-xs font-mono text-slate-700">Contact: {sup.contact_id.slice(0, 8)}...</div>
                        {sup.job_id && (
                          <div className="text-[10px] text-slate-400 font-mono">Job: {sup.job_id.slice(0, 8)}...</div>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-900">
                          {sup.reason}
                        </span>
                      </TableCell>
                      <TableCell>
                        <pre className="text-[10px] bg-slate-50 p-1.5 rounded max-w-sm truncate text-slate-700 font-mono">
                          {JSON.stringify(sup.details)}
                        </pre>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}

      {/* TAB 5: WORKER & SETTINGS */}
      {activeTab === 'settings' && (
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Sliders className="h-5 w-5 text-teal-600" />
                Clinic Operating Windows & Worker Configuration
              </CardTitle>
              <CardDescription className="text-xs">
                Timezone-aware dispatch policies and safety parameters for Physio One.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="p-3 bg-slate-50 rounded border border-slate-200">
                  <div className="font-semibold text-slate-700">Operating Timezone</div>
                  <div className="font-mono text-base font-bold text-teal-700 mt-1">
                    {settings?.default_timezone || 'Asia/Kolkata'}
                  </div>
                  <div className="text-slate-500 mt-1">Mandatory IST timezone for all scheduling offsets.</div>
                </div>
                <div className="p-3 bg-slate-50 rounded border border-slate-200">
                  <div className="font-semibold text-slate-700">Business Hours Window</div>
                  <div className="font-mono text-base font-bold text-teal-700 mt-1">
                    {settings?.business_hours_start || '09:00'} - {settings?.business_hours_end || '20:00'} IST
                  </div>
                  <div className="text-slate-500 mt-1">Patient reminders & follow-ups sent only in this window.</div>
                </div>
                <div className="p-3 bg-slate-50 rounded border border-slate-200">
                  <div className="font-semibold text-slate-700">Quiet Hours Protection</div>
                  <div className="font-mono text-base font-bold text-amber-700 mt-1">
                    {settings?.quiet_hours_start || '21:00'} - {settings?.quiet_hours_end || '09:00'} IST
                  </div>
                  <div className="text-slate-500 mt-1">All outbound automation strictly deferred until 09:00 IST.</div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs pt-2">
                <div className="border p-2.5 rounded">
                  <span className="text-slate-500">Worker Scan Interval</span>
                  <div className="font-bold text-sm text-slate-800 mt-0.5">
                    {settings?.worker_scan_interval_seconds || 15}s
                  </div>
                </div>
                <div className="border p-2.5 rounded">
                  <span className="text-slate-500">Max Retry Attempts</span>
                  <div className="font-bold text-sm text-slate-800 mt-0.5">
                    {settings?.max_retries || 5} attempts
                  </div>
                </div>
                <div className="border p-2.5 rounded">
                  <span className="text-slate-500">Contact Cooldown</span>
                  <div className="font-bold text-sm text-slate-800 mt-0.5">
                    {settings?.default_cooldown_hours || 24} hours
                  </div>
                </div>
                <div className="border p-2.5 rounded">
                  <span className="text-slate-500">Rate Limit Per Min</span>
                  <div className="font-bold text-sm text-slate-800 mt-0.5">
                    {settings?.rate_limit_per_minute || 60} msgs
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Manual Service Trigger Controls */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Zap className="h-5 w-5 text-amber-600" />
                Service Triggers & Diagnostics
              </CardTitle>
              <CardDescription className="text-xs">
                Manually trigger worker cycles and inactivity scanner for testing and on-demand queue processing.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                <Button
                  variant="primary"
                  onClick={handleTriggerWorker}
                  disabled={actionLoading}
                  className="bg-teal-600 hover:bg-teal-700 text-white flex items-center justify-center gap-2"
                >
                  <Play className="h-4 w-4" />
                  Run Automation Worker Cycle Now
                </Button>
                <Button
                  variant="outline"
                  onClick={handleTriggerInactivityScan}
                  disabled={actionLoading}
                  className="flex items-center justify-center gap-2"
                >
                  <Clock className="h-4 w-4 text-teal-600" />
                  Run Inactivity Scan (15-min Batch)
                </Button>
              </div>
              <p className="text-[11px] text-slate-500">
                Worker cycles lock due jobs using PostgreSQL row leasing (`SKIP LOCKED`) and enforce all 12 eligibility checks before dispatch.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* MODAL: Kill Switch Confirmation */}
      <Dialog
        isOpen={showKillSwitchConfirm}
        onClose={() => setShowKillSwitchConfirm(false)}
        title={pendingKillSwitchValue ? 'Confirm Outbound Activation' : 'Confirm Kill Switch Engagement'}
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            {pendingKillSwitchValue
              ? 'Are you sure you want to ACTIVATE automated WhatsApp outbound messaging? Once active, eligible scheduled jobs will be sent via Meta/YCloud during permitted business hours.'
              : 'Are you sure you want to ENGAGE the kill switch? All scheduled automated outbound WhatsApp dispatch will be immediately paused. Queued jobs will be held or suppressed.'}
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" onClick={() => setShowKillSwitchConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant={pendingKillSwitchValue ? 'primary' : 'destructive'}
              size="sm"
              onClick={handleToggleKillSwitch}
              disabled={actionLoading}
              className={pendingKillSwitchValue ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : ''}
            >
              {pendingKillSwitchValue ? 'Confirm & Activate' : 'Engage Kill Switch'}
            </Button>
          </div>
        </div>
      </Dialog>

      {/* MODAL: Job Details */}
      {selectedJob && (
        <Dialog
          isOpen={showJobModal}
          onClose={() => setShowJobModal(false)}
          title={`Job Details: ${selectedJob.id.slice(0, 8)}...`}
        >
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-slate-400">Recipient:</span>
                <div className="font-semibold text-slate-900">{selectedJob.contact_name || 'Patient'}</div>
                <div className="font-mono text-slate-600">{selectedJob.contact_phone || selectedJob.contact_id}</div>
              </div>
              <div>
                <span className="text-slate-400">Status:</span>
                <div>
                  <Badge variant="outline" className="font-semibold uppercase">
                    {selectedJob.status}
                  </Badge>
                </div>
              </div>
            </div>

            <div>
              <span className="text-slate-400">Scheduled For (IST):</span>
              <div className="font-semibold text-slate-800">{formatISTDateTime(selectedJob.scheduled_for)}</div>
            </div>

            {selectedJob.suppression_reason && (
              <div className="bg-amber-50 border border-amber-200 p-2.5 rounded text-amber-900">
                <span className="font-semibold block">Suppression Reason:</span>
                {selectedJob.suppression_reason}
              </div>
            )}

            <div>
              <span className="text-slate-400">Idempotency Key:</span>
              <div className="font-mono text-[11px] text-slate-700 bg-slate-100 p-1 rounded truncate">
                {selectedJob.idempotency_key}
              </div>
            </div>

            <div>
              <span className="text-slate-400">Payload:</span>
              <pre className="bg-slate-900 text-slate-100 p-2.5 rounded overflow-x-auto text-[10px] font-mono max-h-40">
                {JSON.stringify(selectedJob.payload, null, 2)}
              </pre>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              {canManage && ['scheduled', 'queued'].includes(selectedJob.status) && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleCancelJob(selectedJob.id)}
                  disabled={actionLoading}
                >
                  Cancel Job
                </Button>
              )}
              {canManage && (selectedJob.status === 'failed' || selectedJob.status === 'suppressed') && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRetryJob(selectedJob.id)}
                  disabled={actionLoading}
                >
                  Retry Job
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => setShowJobModal(false)}>
                Close
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* MODAL: Template Preview */}
      {selectedTemplate && (
        <Dialog
          isOpen={showTemplateModal}
          onClose={() => setShowTemplateModal(false)}
          title={`WhatsApp Template: ${selectedTemplate.name}`}
        >
          <div className="space-y-3 text-xs">
            <div className="flex items-center gap-2">
              <Badge className="bg-emerald-600 text-white">{selectedTemplate.approval_status}</Badge>
              <span className="text-slate-500">Category: {selectedTemplate.category}</span>
              <span className="text-slate-500">Language: {selectedTemplate.language}</span>
            </div>

            <div className="p-3 bg-teal-50/50 border border-teal-200 rounded text-slate-800 text-sm leading-relaxed">
              {selectedTemplate.body}
            </div>

            <div>
              <span className="font-semibold text-slate-700 block mb-1">Interpolated Variables:</span>
              <div className="flex flex-wrap gap-1.5">
                {selectedTemplate.variables.map((v) => (
                  <span key={v} className="bg-slate-100 text-slate-800 px-2 py-0.5 rounded font-mono text-xs">
                    {`{{${v}}}`}
                  </span>
                ))}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="outline" size="sm" onClick={() => setShowTemplateModal(false)}>
                Close
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* MODAL: Schedule Staff Follow-up */}
      <Dialog
        isOpen={showCreateFollowupModal}
        onClose={() => setShowCreateFollowupModal(false)}
        title="Schedule Patient Follow-up"
      >
        <form onSubmit={handleCreateStaffFollowup} className="space-y-3 text-xs">
          <div>
            <label className="font-medium text-slate-700 block mb-1">Contact ID (UUID):</label>
            <Input
              placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
              value={newFollowupContactId}
              onChange={(e) => setNewFollowupContactId(e.target.value)}
              required
              className="h-8 text-xs font-mono"
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Scheduled Send Time (IST):</label>
            <Input
              type="datetime-local"
              value={newFollowupScheduledFor}
              onChange={(e) => setNewFollowupScheduledFor(e.target.value)}
              required
              className="h-8 text-xs"
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Reason / Clinical Purpose:</label>
            <Input
              placeholder="e.g. Post-consultation exercise plan check-in"
              value={newFollowupReason}
              onChange={(e) => setNewFollowupReason(e.target.value)}
              required
              className="h-8 text-xs"
            />
          </div>

          <div>
            <label className="font-medium text-slate-700 block mb-1">Message Text (Optional if template used):</label>
            <textarea
              rows={3}
              placeholder="Hello, Dr. Physio One is checking in on your recovery progress..."
              value={newFollowupMessage}
              onChange={(e) => setNewFollowupMessage(e.target.value)}
              className="w-full text-xs p-2 border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-teal-500"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" type="button" onClick={() => setShowCreateFollowupModal(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              type="submit"
              disabled={actionLoading}
              className="bg-teal-600 hover:bg-teal-700 text-white"
            >
              Schedule Follow-up
            </Button>
          </div>
        </form>
      </Dialog>

      {/* MODAL: Worker Run Diagnostics Result */}
      <Dialog
        isOpen={showWorkerResultModal}
        onClose={() => setShowWorkerResultModal(false)}
        title="Worker Run Diagnostics"
      >
        <div className="space-y-3 text-xs">
          {workerResult && (
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-50 p-2 rounded">
                <span className="text-slate-500 block">Scanned Jobs:</span>
                <span className="font-bold text-base text-slate-800">{String(workerResult.scanned_count)}</span>
              </div>
              <div className="bg-slate-50 p-2 rounded">
                <span className="text-slate-500 block">Locked with Lease:</span>
                <span className="font-bold text-base text-slate-800">{String(workerResult.locked_count)}</span>
              </div>
              <div className="bg-emerald-50 p-2 rounded">
                <span className="text-emerald-700 block">Sent Successfully:</span>
                <span className="font-bold text-base text-emerald-800">{String(workerResult.sent_count)}</span>
              </div>
              <div className="bg-amber-50 p-2 rounded">
                <span className="text-amber-700 block">Suppressed / Deferred:</span>
                <span className="font-bold text-base text-amber-800">{String(workerResult.suppressed_count)}</span>
              </div>
            </div>
          )}

          <div className="flex justify-end pt-2">
            <Button variant="outline" size="sm" onClick={() => setShowWorkerResultModal(false)}>
              Done
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
