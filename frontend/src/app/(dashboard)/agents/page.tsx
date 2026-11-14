'use client';

import React, { useState, useEffect } from 'react';
import {
  Bot,
  Plus,
  Play,
  History,
  Settings2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  RefreshCw,
  Send,
  Sliders,
  ShieldAlert,
  Clock,
  Zap,
  Code2,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';
import {
  apiClient,
  AIAgent,
  AIAgentVersion,
  AIAgentTestResponse,
  AgentExecutionSession,
  AIModel,
  RegisteredTool,
} from '@/lib/api-client';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Dialog } from '@/components/ui/dialog';

export default function AgentsPage() {
  const [agents, setAgents] = useState<AIAgent[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);
  const [tools, setTools] = useState<RegisteredTool[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modals & Panels
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [showEditModal, setShowEditModal] = useState<boolean>(false);
  const [showVersionModal, setShowVersionModal] = useState<boolean>(false);
  const [showTestModal, setShowTestModal] = useState<boolean>(false);
  const [showHistoryModal, setShowHistoryModal] = useState<boolean>(false);

  // Selected agent state
  const [selectedAgent, setSelectedAgent] = useState<AIAgent | null>(null);
  const [versions, setVersions] = useState<AIAgentVersion[]>([]);
  const [loadingVersions, setLoadingVersions] = useState<boolean>(false);
  const [executions, setExecutions] = useState<AgentExecutionSession[]>([]);
  const [loadingExecutions, setLoadingExecutions] = useState<boolean>(false);

  // Form states
  const [agentForm, setAgentForm] = useState({
    name: '',
    description: '',
    primary_model_id: '',
    fallback_model_id: '',
    system_prompt: '',
    temperature: 0.2,
    max_tokens: 1000,
    allowed_tools: ['check_availability', 'find_patient'],
    max_execution_steps: 5,
    execution_timeout_seconds: 60,
    context_budget_tokens: 4000,
    is_active: true,
    change_summary: '',
  });
  const [submitting, setSubmitting] = useState<boolean>(false);

  // Test Console state
  const [testPrompt, setTestPrompt] = useState<string>('Are there consultation slots available next Tuesday?');
  const [allowFallback, setAllowFallback] = useState<boolean>(false);
  const [runningTest, setRunningTest] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<AIAgentTestResponse | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [agentList, modelList, toolList] = await Promise.all([
        apiClient.getAgents(),
        apiClient.getLLMModels().catch(() => []),
        apiClient.getTools().catch(() => []),
      ]);
      setAgents(agentList);
      setModels(modelList);
      setTools(toolList);
    } catch (err: any) {
      setError(err.message || 'Failed to load AI Agents.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Handlers for Modals
  const openCreateModal = () => {
    const defaultModel = models.find((m) => m.model_identifier === 'gpt-4o-mini') || models[0];
    const defaultFallback = models.find((m) => m.model_identifier === 'claude-3-5-sonnet-20241022');
    setAgentForm({
      name: '',
      description: '',
      primary_model_id: defaultModel?.id || '',
      fallback_model_id: defaultFallback?.id || '',
      system_prompt:
        'You are an AI assistant for Physio One Clinic. Operating hours are Monday to Saturday, 09:00 AM to 08:00 PM IST. Closed on Sundays.',
      temperature: 0.2,
      max_tokens: 1000,
      allowed_tools: ['check_availability', 'find_patient'],
      max_execution_steps: 5,
      execution_timeout_seconds: 60,
      context_budget_tokens: 4000,
      is_active: true,
      change_summary: '',
    });
    setShowCreateModal(true);
  };

  const openEditModal = (agent: AIAgent) => {
    setSelectedAgent(agent);
    setAgentForm({
      name: agent.name,
      description: agent.description || '',
      primary_model_id: agent.primary_model_id,
      fallback_model_id: agent.fallback_model_id || '',
      system_prompt: agent.system_prompt,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens,
      allowed_tools: agent.allowed_tools,
      max_execution_steps: agent.max_execution_steps,
      execution_timeout_seconds: agent.execution_timeout_seconds,
      context_budget_tokens: agent.context_budget_tokens,
      is_active: agent.is_active,
      change_summary: '',
    });
    setShowEditModal(true);
  };

  const openVersionHistory = async (agent: AIAgent) => {
    setSelectedAgent(agent);
    setShowVersionModal(true);
    setLoadingVersions(true);
    try {
      const v = await apiClient.getAgentVersions(agent.id);
      setVersions(v);
    } catch (err: any) {
      setError(err.message || 'Failed to load version history.');
    } finally {
      setLoadingVersions(false);
    }
  };

  const openExecutionHistory = async (agent: AIAgent) => {
    setSelectedAgent(agent);
    setShowHistoryModal(true);
    setLoadingExecutions(true);
    try {
      const execs = await apiClient.getAgentExecutions(agent.id, 20);
      setExecutions(execs);
    } catch (err: any) {
      setError(err.message || 'Failed to load execution sessions.');
    } finally {
      setLoadingExecutions(false);
    }
  };

  const openTestConsole = (agent: AIAgent) => {
    setSelectedAgent(agent);
    setTestResult(null);
    setShowTestModal(true);
  };

  const handleCreateAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.createAgent({
        name: agentForm.name,
        description: agentForm.description || undefined,
        primary_model_id: agentForm.primary_model_id,
        fallback_model_id: agentForm.fallback_model_id || undefined,
        system_prompt: agentForm.system_prompt,
        temperature: Number(agentForm.temperature),
        max_tokens: Number(agentForm.max_tokens),
        allowed_tools: agentForm.allowed_tools,
        max_execution_steps: Number(agentForm.max_execution_steps),
        execution_timeout_seconds: Number(agentForm.execution_timeout_seconds),
        context_budget_tokens: Number(agentForm.context_budget_tokens),
        is_active: agentForm.is_active,
      });
      setSuccessMsg(`Agent '${agentForm.name}' created successfully.`);
      setShowCreateModal(false);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to create agent.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.updateAgent(selectedAgent.id, {
        name: agentForm.name,
        description: agentForm.description || undefined,
        primary_model_id: agentForm.primary_model_id,
        fallback_model_id: agentForm.fallback_model_id || undefined,
        system_prompt: agentForm.system_prompt,
        temperature: Number(agentForm.temperature),
        max_tokens: Number(agentForm.max_tokens),
        allowed_tools: agentForm.allowed_tools,
        max_execution_steps: Number(agentForm.max_execution_steps),
        execution_timeout_seconds: Number(agentForm.execution_timeout_seconds),
        context_budget_tokens: Number(agentForm.context_budget_tokens),
        is_active: agentForm.is_active,
        change_summary: agentForm.change_summary || undefined,
      });
      setSuccessMsg(`Agent '${agentForm.name}' updated successfully.`);
      setShowEditModal(false);
      await loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to update agent.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRunTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent || !testPrompt.trim()) return;
    setRunningTest(true);
    setError(null);
    try {
      const res = await apiClient.testAgent(selectedAgent.id, {
        message: testPrompt.trim(),
        allow_fallback: allowFallback,
      });
      setTestResult(res);
    } catch (err: any) {
      setError(err.message || 'Agent test execution failed.');
    } finally {
      setRunningTest(false);
    }
  };

  const toggleTool = (toolName: string) => {
    setAgentForm((prev) => {
      const exists = prev.allowed_tools.includes(toolName);
      if (exists) {
        return { ...prev, allowed_tools: prev.allowed_tools.filter((t) => t !== toolName) };
      } else {
        return { ...prev, allowed_tools: [...prev.allowed_tools, toolName] };
      }
    });
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <Bot className="h-7 w-7 text-emerald-600" />
            AI Agents & Receptionist Runtime
          </h1>
          <p className="text-sm text-slate-500">
            Provider-independent LLM gateway, agent configurations, version snapshots, and test execution console.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={loadData} disabled={loading} className="gap-2">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={openCreateModal} className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white">
            <Plus className="h-4 w-4" />
            Create Agent
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" title="Error">
          {error}
        </Alert>
      )}

      {successMsg && (
        <Alert variant="success" title="Success">
          {successMsg}
        </Alert>
      )}

      {/* Notice Banner */}
      <Alert variant="info" title="Task 7 Foundation — Controlled Receptionist Scaffolding">
        Deepti receptionist persona and multi-provider runtime are fully established. Autonomous WhatsApp messaging and
        live appointment creation remain strictly gated until subsequent milestone activation.
      </Alert>

      {/* Agents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading && agents.length === 0 ? (
          <div className="col-span-full py-12 text-center text-slate-400">Loading configured agents...</div>
        ) : agents.length === 0 ? (
          <div className="col-span-full py-12 text-center text-slate-400">No AI agents configured yet.</div>
        ) : (
          agents.map((agent) => (
            <Card key={agent.id} className="flex flex-col justify-between hover:shadow-md transition-shadow border-slate-200">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-emerald-50 text-emerald-700 rounded-lg">
                      <Bot className="h-5 w-5" />
                    </div>
                    <div>
                      <CardTitle className="text-base font-semibold text-slate-900">{agent.name}</CardTitle>
                      <span className="text-xs text-slate-400">v{agent.current_version}</span>
                    </div>
                  </div>
                  <Badge variant={agent.is_active ? 'success' : 'secondary'}>
                    {agent.is_active ? 'Active' : 'Disabled'}
                  </Badge>
                </div>
                <CardDescription className="text-xs text-slate-500 mt-2 line-clamp-2">
                  {agent.description || 'No description provided.'}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4 text-xs">
                {/* Specs */}
                <div className="bg-slate-50 p-3 rounded-lg space-y-1.5 border border-slate-100">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Primary Model:</span>
                    <span className="font-medium text-slate-800">
                      {agent.primary_provider_name} / {agent.primary_model_identifier}
                    </span>
                  </div>
                  {agent.fallback_model_identifier && (
                    <div className="flex justify-between">
                      <span className="text-slate-500">Fallback:</span>
                      <span className="font-medium text-slate-700">
                        {agent.fallback_provider_name} / {agent.fallback_model_identifier}
                      </span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-slate-500">Temperature:</span>
                    <span className="font-medium text-slate-800">{agent.temperature}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Allowed Tools:</span>
                    <span className="font-medium text-emerald-700">{agent.allowed_tools.length} active</span>
                  </div>
                </div>

                {/* Actions */}
                <div className="pt-2 flex items-center justify-between gap-2 border-t border-slate-100">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1 gap-1 text-emerald-700 border-emerald-200 hover:bg-emerald-50"
                    onClick={() => openTestConsole(agent)}
                  >
                    <Play className="h-3.5 w-3.5" />
                    Test
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openVersionHistory(agent)} title="Version History">
                    <History className="h-4 w-4 text-slate-500" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openExecutionHistory(agent)} title="Execution Logs">
                    <Clock className="h-4 w-4 text-slate-500" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openEditModal(agent)} title="Edit Configuration">
                    <Settings2 className="h-4 w-4 text-slate-500" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* CREATE AGENT DIALOG */}
      <Dialog
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New AI Agent"
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <form onSubmit={handleCreateAgent} className="space-y-4 text-sm mt-3">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Agent Name *</label>
                <Input
                  value={agentForm.name}
                  onChange={(e) => setAgentForm({ ...agentForm, name: e.target.value })}
                  placeholder="e.g. Deepti Clinic Assistant"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Primary Model *</label>
                <select
                  value={agentForm.primary_model_id}
                  onChange={(e) => setAgentForm({ ...agentForm, primary_model_id: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm bg-white"
                  required
                >
                  <option value="">Select primary model</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.provider_name} — {m.display_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
              <Input
                value={agentForm.description}
                onChange={(e) => setAgentForm({ ...agentForm, description: e.target.value })}
                placeholder="Clinical purpose and scope of agent"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Fallback Model (Optional)</label>
                <select
                  value={agentForm.fallback_model_id}
                  onChange={(e) => setAgentForm({ ...agentForm, fallback_model_id: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm bg-white"
                >
                  <option value="">None (Fallback disabled)</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.provider_name} — {m.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Temperature</label>
                  <Input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={agentForm.temperature}
                    onChange={(e) => setAgentForm({ ...agentForm, temperature: parseFloat(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Max Tokens</label>
                  <Input
                    type="number"
                    min="100"
                    max="4000"
                    value={agentForm.max_tokens}
                    onChange={(e) => setAgentForm({ ...agentForm, max_tokens: parseInt(e.target.value) })}
                  />
                </div>
              </div>
            </div>

            {/* Allowed Tools Whitelist */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Permitted Tools</label>
              <div className="grid grid-cols-2 gap-2 border border-slate-200 p-2.5 rounded-lg bg-slate-50">
                {tools.map((t) => (
                  <label key={t.name} className="flex items-center gap-2 text-xs cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={agentForm.allowed_tools.includes(t.name)}
                      onChange={() => toggleTool(t.name)}
                      className="rounded text-emerald-600 focus:ring-emerald-500"
                    />
                    <span className="font-mono text-slate-800">{t.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">System Instructions *</label>
              <textarea
                value={agentForm.system_prompt}
                onChange={(e) => setAgentForm({ ...agentForm, system_prompt: e.target.value })}
                rows={7}
                className="w-full px-3 py-2 border border-slate-200 rounded-md text-xs font-mono bg-white"
                placeholder="Persona guidelines, clinic policies, guardrails..."
                required
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
              <Button type="button" variant="outline" onClick={() => setShowCreateModal(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                {submitting ? 'Creating...' : 'Create Agent'}
              </Button>
            </div>
          </form>
      </Dialog>

      {/* EDIT AGENT DIALOG */}
      <Dialog
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title={`Edit Agent — ${selectedAgent?.name || ''}`}
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <form onSubmit={handleUpdateAgent} className="space-y-4 text-sm mt-3">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Agent Name *</label>
                <Input
                  value={agentForm.name}
                  onChange={(e) => setAgentForm({ ...agentForm, name: e.target.value })}
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Primary Model *</label>
                <select
                  value={agentForm.primary_model_id}
                  onChange={(e) => setAgentForm({ ...agentForm, primary_model_id: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm bg-white"
                  required
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.provider_name} — {m.display_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Description</label>
              <Input
                value={agentForm.description}
                onChange={(e) => setAgentForm({ ...agentForm, description: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Fallback Model</label>
                <select
                  value={agentForm.fallback_model_id}
                  onChange={(e) => setAgentForm({ ...agentForm, fallback_model_id: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm bg-white"
                >
                  <option value="">None (Fallback disabled)</option>
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.provider_name} — {m.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Temperature</label>
                  <Input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={agentForm.temperature}
                    onChange={(e) => setAgentForm({ ...agentForm, temperature: parseFloat(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Max Tokens</label>
                  <Input
                    type="number"
                    min="100"
                    max="4000"
                    value={agentForm.max_tokens}
                    onChange={(e) => setAgentForm({ ...agentForm, max_tokens: parseInt(e.target.value) })}
                  />
                </div>
              </div>
            </div>

            {/* Allowed Tools */}
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Permitted Tools</label>
              <div className="grid grid-cols-2 gap-2 border border-slate-200 p-2.5 rounded-lg bg-slate-50">
                {tools.map((t) => (
                  <label key={t.name} className="flex items-center gap-2 text-xs cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={agentForm.allowed_tools.includes(t.name)}
                      onChange={() => toggleTool(t.name)}
                      className="rounded text-emerald-600 focus:ring-emerald-500"
                    />
                    <span className="font-mono text-slate-800">{t.name}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">System Instructions *</label>
              <textarea
                value={agentForm.system_prompt}
                onChange={(e) => setAgentForm({ ...agentForm, system_prompt: e.target.value })}
                rows={7}
                className="w-full px-3 py-2 border border-slate-200 rounded-md text-xs font-mono bg-white"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Version Change Summary (Documented in historical snapshots)
              </label>
              <Input
                value={agentForm.change_summary}
                onChange={(e) => setAgentForm({ ...agentForm, change_summary: e.target.value })}
                placeholder="e.g. Added holiday timings and updated greeting tone"
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
              <Button type="button" variant="outline" onClick={() => setShowEditModal(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                {submitting ? 'Saving...' : 'Save & Increment Version'}
              </Button>
            </div>
          </form>
      </Dialog>

      {/* VERSION HISTORY MODAL */}
      <Dialog
        isOpen={showVersionModal}
        onClose={() => setShowVersionModal(false)}
        title={`Version History — ${selectedAgent?.name || ''}`}
        className="max-w-2xl max-h-[85vh] overflow-y-auto"
      >
        <div className="space-y-4 mt-3">
          {loadingVersions ? (
            <div className="text-center py-8 text-slate-400">Loading version history...</div>
          ) : versions.length === 0 ? (
            <div className="text-center py-8 text-slate-400">No version snapshots found.</div>
          ) : (
            versions.map((ver) => (
              <div key={ver.id} className="p-4 border border-slate-200 rounded-lg space-y-2 bg-slate-50">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-900">Version {ver.version_number}</span>
                  <span className="text-xs text-slate-400">{new Date(ver.created_at).toLocaleString()}</span>
                </div>
                <p className="text-xs text-slate-600 font-medium">
                  Change: {ver.change_summary || 'No change description recorded.'}
                </p>
                <div className="flex gap-4 text-xs text-slate-500">
                  <span>Model: {ver.model_identifier || 'Standard'}</span>
                  <span>Temp: {ver.temperature}</span>
                  <span>Tools: {(ver.allowed_tools || []).join(', ') || 'None'}</span>
                </div>
                <details className="text-xs text-slate-600">
                  <summary className="cursor-pointer font-medium text-emerald-700">View System Instructions</summary>
                  <pre className="mt-2 p-2 bg-white rounded border border-slate-200 whitespace-pre-wrap font-mono text-[11px]">
                    {ver.system_prompt}
                  </pre>
                </details>
              </div>
            ))
          )}
        </div>
      </Dialog>

      {/* EXECUTION HISTORY MODAL */}
      <Dialog
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        title={`Execution Session Logs — ${selectedAgent?.name || ''}`}
        className="max-w-3xl max-h-[85vh] overflow-y-auto"
      >
        <div className="space-y-3 mt-3">
          {loadingExecutions ? (
            <div className="text-center py-8 text-slate-400">Loading execution sessions...</div>
          ) : executions.length === 0 ? (
            <div className="text-center py-8 text-slate-400">No execution sessions recorded yet.</div>
          ) : (
            executions.map((s) => (
              <div key={s.id} className="p-3 border border-slate-200 rounded-lg bg-white space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant={s.status === 'completed' ? 'success' : s.status === 'failed' ? 'destructive' : 'secondary'}>
                      {s.status}
                    </Badge>
                    <span className="font-mono text-slate-600">{s.id.slice(0, 8)}...</span>
                  </div>
                  <span className="text-slate-400">{new Date(s.created_at).toLocaleString()}</span>
                </div>
                <div className="flex gap-4 text-slate-600">
                  <span>Steps: {s.total_execution_steps}</span>
                  <span>Tokens: {s.total_input_tokens + s.total_output_tokens}</span>
                  {s.duration_ms && <span>Latency: {s.duration_ms}ms</span>}
                </div>
                {s.error_message && <div className="text-rose-600 bg-rose-50 p-2 rounded">Error: {s.error_message}</div>}
                {s.executions && s.executions.length > 0 && (
                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    {s.executions.map((step) => (
                      <div key={step.step_number} className="p-2 bg-slate-50 rounded font-mono text-[11px] space-y-1">
                        <div className="flex justify-between font-semibold text-slate-700">
                          <span>Step {step.step_number}</span>
                          <span>{step.duration_ms}ms</span>
                        </div>
                        {step.tool_calls && step.tool_calls.length > 0 && (
                          <div className="text-emerald-700">
                            Tool Calls: {step.tool_calls.map((tc: any) => tc.name).join(', ')}
                          </div>
                        )}
                        {step.response_text && (
                          <div className="text-slate-800 line-clamp-2">Response: {step.response_text}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </Dialog>

      {/* TEST CONSOLE MODAL */}
      <Dialog
        isOpen={showTestModal}
        onClose={() => setShowTestModal(false)}
        title={`Isolated Test Console — ${selectedAgent?.name || ''}`}
        className="max-w-3xl max-h-[90vh] overflow-y-auto"
      >

          <div className="space-y-4 mt-2">
            <div className="p-2.5 bg-emerald-50 border border-emerald-100 rounded-lg text-xs text-emerald-800 flex items-start gap-2">
              <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                Isolated Sandbox Mode: Test executions trigger the full agent loop and registered clinical tools without
                sending live WhatsApp messages or mutating active appointment records.
              </span>
            </div>

            <form onSubmit={handleRunTest} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Test Message / Patient Inquiry</label>
                <div className="flex gap-2">
                  <Input
                    value={testPrompt}
                    onChange={(e) => setTestPrompt(e.target.value)}
                    placeholder="Type a clinical inquiry or availability question..."
                    required
                  />
                  <Button
                    type="submit"
                    disabled={runningTest || !testPrompt.trim()}
                    className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white shrink-0"
                  >
                    {runningTest ? (
                      <>
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        Running...
                      </>
                    ) : (
                      <>
                        <Send className="h-4 w-4" />
                        Send Test
                      </>
                    )}
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="fallbackToggle"
                  checked={allowFallback}
                  onChange={(e) => setAllowFallback(e.target.checked)}
                  className="rounded text-emerald-600"
                />
                <label htmlFor="fallbackToggle" className="text-xs text-slate-600 cursor-pointer">
                  Allow fallback provider on rate limit / outage (Primary: {selectedAgent?.primary_model_identifier})
                </label>
              </div>
            </form>

            {/* Test Execution Output */}
            {testResult && (
              <div className="space-y-3 border-t border-slate-200 pt-4 text-xs">
                {/* Metrics Banner */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-50 p-3 rounded-lg border border-slate-200">
                  <div>
                    <span className="text-slate-400 block text-[10px]">Status</span>
                    <Badge variant={testResult.status === 'completed' ? 'success' : 'destructive'}>
                      {testResult.status}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Provider / Model</span>
                    <span className="font-semibold text-slate-800">
                      {testResult.provider} / {testResult.model}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Latency</span>
                    <span className="font-semibold text-slate-800">{testResult.duration_ms}ms</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Tokens (In / Out)</span>
                    <span className="font-semibold text-slate-800">
                      {testResult.total_input_tokens} / {testResult.total_output_tokens}
                    </span>
                  </div>
                </div>

                {/* Generated Answer */}
                <div className="p-3 bg-white border border-slate-200 rounded-lg space-y-1">
                  <span className="font-semibold text-slate-700 block">Generated Conversational Response:</span>
                  <p className="text-slate-900 whitespace-pre-wrap leading-relaxed">{testResult.response_text}</p>
                </div>

                {/* Tool Calls Summary */}
                {testResult.tool_calls && testResult.tool_calls.length > 0 && (
                  <div className="space-y-2">
                    <span className="font-semibold text-slate-700 block">
                      Dispatched Tool Calls ({testResult.tool_calls.length}):
                    </span>
                    {testResult.tool_calls.map((tc, idx) => (
                      <div key={idx} className="p-2.5 bg-slate-50 border border-slate-200 rounded font-mono text-[11px] space-y-1">
                        <div className="flex justify-between text-emerald-800 font-semibold">
                          <span>
                            Step {tc.step}: {tc.name}
                          </span>
                          <span className="text-slate-500">{tc.id}</span>
                        </div>
                        <div className="text-slate-600">Arguments: {JSON.stringify(tc.arguments)}</div>
                        <div className="text-slate-800 bg-white p-1.5 rounded border border-slate-200">
                          Result: {JSON.stringify(tc.result)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {testResult.error_message && (
                  <div className="p-3 bg-rose-50 text-rose-700 rounded-lg">
                    Execution Error: {testResult.error_message}
                  </div>
                )}
              </div>
            )}
          </div>
      </Dialog>
    </div>
  );
}
