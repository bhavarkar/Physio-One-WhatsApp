"use client";

import React, { useState, useEffect } from "react";
import {
  MessageSquare,
  Shield,
  Key,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Plus,
  RefreshCw,
  Send,
  Lock,
  Phone,
  Server,
  Building2,
  Cpu,
  Zap,
  Sliders,
  Eye,
  EyeOff,
} from "lucide-react";
import {
  apiClient,
  WhatsAppConnection,
  ConnectionTestResult,
  TestMessageResult,
  AIProvider,
  AIProviderTestResult,
} from "@/lib/api-client";

export default function SettingsPage() {
  const [activeSettingsTab, setActiveSettingsTab] = useState<"whatsapp" | "llm">("whatsapp");

  // WhatsApp states
  const [connections, setConnections] = useState<WhatsAppConnection[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Modal state
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [savingConnection, setSavingConnection] = useState<boolean>(false);
  const [newConn, setNewConn] = useState({
    provider: "meta" as "meta" | "ycloud",
    account_name: "",
    display_phone_number: "",
    phone_number_id: "",
    business_account_id: "",
    webhook_verify_token: "",
    access_token: "",
    secret_key: "",
    is_active: true,
  });

  // Test action states
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    id: string;
    result: ConnectionTestResult;
  } | null>(null);

  // Send test message dialog state
  const [testMsgModal, setTestMsgModal] = useState<{
    id: string;
    phone: string;
  } | null>(null);
  const [testRecipient, setTestRecipient] = useState<string>("");
  const [testMessageText, setTestMessageText] = useState<string>(
    "Hello from Physio One WhatsApp Integration! This is a test message."
  );
  const [sendingTestMsg, setSendingTestMsg] = useState<boolean>(false);
  const [testMsgResult, setTestMsgResult] = useState<TestMessageResult | null>(
    null
  );

  // LLM Provider States
  const [llmProviders, setLlmProviders] = useState<AIProvider[]>([]);
  const [loadingLLM, setLoadingLLM] = useState<boolean>(false);
  const [testingLlmId, setTestingLlmId] = useState<string | null>(null);
  const [llmTestResult, setLlmTestResult] = useState<{
    id: string;
    result: AIProviderTestResult;
  } | null>(null);
  const [editProviderModal, setEditProviderModal] = useState<AIProvider | null>(null);
  const [editProviderForm, setEditProviderForm] = useState({
    base_url: "",
    api_key: "",
    is_enabled: true,
  });
  const [savingProvider, setSavingProvider] = useState<boolean>(false);
  const [showApiKey, setShowApiKey] = useState<boolean>(false);

  const loadConnections = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getWhatsAppConnections();
      setConnections(data);
    } catch (err: any) {
      setError(err.message || "Failed to load WhatsApp connections.");
    } finally {
      setLoading(false);
    }
  };

  const loadLLMProviders = async () => {
    setLoadingLLM(true);
    setError(null);
    try {
      const data = await apiClient.getLLMProviders();
      setLlmProviders(data);
    } catch (err: any) {
      setError(err.message || "Failed to load LLM providers.");
    } finally {
      setLoadingLLM(false);
    }
  };

  useEffect(() => {
    loadConnections();
    loadLLMProviders();
  }, []);

  const handleCreateConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConnection(true);
    setError(null);
    setActionSuccess(null);
    try {
      await apiClient.createWhatsAppConnection({
        provider: newConn.provider,
        account_name: newConn.account_name || `${newConn.provider === 'meta' ? 'Meta' : 'YCloud'} Connection`,
        phone_number_id: newConn.phone_number_id,
        display_phone_number: newConn.display_phone_number,
        business_account_id: newConn.business_account_id || undefined,
        webhook_verify_token: newConn.webhook_verify_token,
        access_token: newConn.access_token,
        secret_key: newConn.secret_key || undefined,
        is_active: newConn.is_active,
      });
      setActionSuccess("WhatsApp provider connection configured successfully.");
      setShowAddModal(false);
      setNewConn({
        provider: "meta",
        account_name: "",
        display_phone_number: "",
        phone_number_id: "",
        business_account_id: "",
        webhook_verify_token: "",
        access_token: "",
        secret_key: "",
        is_active: true,
      });
      await loadConnections();
    } catch (err: any) {
      setError(err.message || "Failed to create connection.");
    } finally {
      setSavingConnection(false);
    }
  };

  const handleTestConnection = async (id: string) => {
    setTestingId(id);
    setTestResult(null);
    setError(null);
    try {
      const result = await apiClient.testWhatsAppConnection(id);
      setTestResult({ id, result });
      await loadConnections();
    } catch (err: any) {
      setError(err.message || "Failed to perform provider handshake test.");
    } finally {
      setTestingId(null);
    }
  };

  const handleSendTestMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testMsgModal) return;
    setSendingTestMsg(true);
    setError(null);
    try {
      const result = await apiClient.sendWhatsAppTestMessage(testMsgModal.id, {
        recipient_phone: testRecipient,
        message_text: testMessageText,
      });
      setTestMsgResult(result);
      setActionSuccess("Test message dispatched successfully.");
      await loadConnections();
    } catch (err: any) {
      setError(err.message || "Failed to send test message.");
    } finally {
      setSendingTestMsg(false);
    }
  };

  const toggleConnectionStatus = async (
    conn: WhatsAppConnection,
    newStatus: boolean
  ) => {
    setError(null);
    setActionSuccess(null);
    try {
      await apiClient.updateWhatsAppConnection(conn.id, {
        is_active: newStatus,
      });
      setActionSuccess(
        `Connection for ${conn.display_phone_number} ${
          newStatus ? "activated" : "deactivated"
        }.`
      );
      await loadConnections();
    } catch (err: any) {
      setError(err.message || "Failed to update connection status.");
    }
  };

  // LLM Handlers
  const handleTestLLMProvider = async (providerId: string) => {
    setTestingLlmId(providerId);
    setError(null);
    setActionSuccess(null);
    try {
      const res = await apiClient.testLLMProvider(providerId);
      setLlmTestResult({ id: providerId, result: res });
      if (res.is_valid) {
        setActionSuccess(`LLM connection valid (${res.latency_ms}ms). Detected models: ${res.detected_models.join(', ')}`);
      } else {
        setError(`LLM provider test reported issue: ${res.error_message || 'Unhealthy'}`);
      }
      await loadLLMProviders();
    } catch (err: any) {
      setError(err.message || "Failed to test LLM provider.");
    } finally {
      setTestingLlmId(null);
    }
  };

  const openEditProvider = (p: AIProvider) => {
    setEditProviderModal(p);
    setEditProviderForm({
      base_url: p.base_url,
      api_key: "",
      is_enabled: p.is_enabled,
    });
    setShowApiKey(false);
  };

  const handleSaveProvider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editProviderModal) return;
    setSavingProvider(true);
    setError(null);
    try {
      await apiClient.updateLLMProvider(editProviderModal.id, {
        base_url: editProviderForm.base_url || undefined,
        api_key: editProviderForm.api_key.trim() || undefined,
        is_enabled: editProviderForm.is_enabled,
      });
      setActionSuccess(`Provider '${editProviderModal.name}' updated successfully.`);
      setEditProviderModal(null);
      await loadLLMProviders();
    } catch (err: any) {
      setError(err.message || "Failed to update provider.");
    } finally {
      setSavingProvider(false);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-gray-200">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            System Settings & WhatsApp Integrations
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure WhatsApp Cloud API, YCloud, and multi-provider LLM gateways.
            All credentials are symmetrically encrypted using Fernet (AES-128-CBC + HMAC-SHA256).
          </p>
        </div>
        {activeSettingsTab === "whatsapp" && (
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Connection
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 gap-6">
        <button
          type="button"
          onClick={() => setActiveSettingsTab("whatsapp")}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
            activeSettingsTab === "whatsapp"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          WhatsApp Connections
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveSettingsTab("llm");
            loadLLMProviders();
          }}
          className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
            activeSettingsTab === "llm"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          <Cpu className="w-4 h-4" />
          LLM Gateway Providers
        </button>
      </div>

      {/* Alerts */}
      {error && (
        <div className="rounded-lg bg-red-50 p-4 border border-red-200 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-red-800">{error}</div>
        </div>
      )}

      {actionSuccess && (
        <div className="rounded-lg bg-emerald-50 p-4 border border-emerald-200 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-emerald-800">{actionSuccess}</div>
        </div>
      )}

      {/* TAB 1: WHATSAPP */}
      {activeSettingsTab === "whatsapp" && (
        <>
          {/* Provider Architecture Guidelines */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <div className="flex items-center gap-3 mb-3">
                <span className="p-2 rounded-lg bg-blue-50 text-blue-700 font-semibold text-xs border border-blue-100 uppercase tracking-wider">
                  Primary Standard
                </span>
                <h2 className="text-base font-semibold text-gray-900">
                  Meta WhatsApp Cloud API
                </h2>
              </div>
              <p className="text-sm text-gray-600 mb-4">
                Direct integration with official Meta Graph API v20.0. Supports text, media, interactive templates, and instant HMAC-SHA256 authenticated webhooks.
              </p>
              <div className="space-y-1.5 text-xs text-gray-500 bg-gray-50 p-3 rounded-lg border border-gray-100">
                <div><strong>Webhook Path:</strong> <code>/api/v1/webhooks/whatsapp/meta</code></div>
                <div><strong>Verification:</strong> GET <code>hub.challenge</code> with Verify Token</div>
                <div><strong>Signature Header:</strong> <code>X-Hub-Signature-256</code></div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <div className="flex items-center gap-3 mb-3">
                <span className="p-2 rounded-lg bg-emerald-50 text-emerald-700 font-semibold text-xs border border-emerald-100 uppercase tracking-wider">
                  Existing Workflow
                </span>
                <h2 className="text-base font-semibold text-gray-900">
                  YCloud Provider
                </h2>
              </div>
              <p className="text-sm text-gray-600 mb-4">
                Preserves ongoing Physio One clinical operations. Fully interoperable with the common internal provider interface and durable webhook queue.
              </p>
              <div className="space-y-1.5 text-xs text-gray-500 bg-gray-50 p-3 rounded-lg border border-gray-100">
                <div><strong>Webhook Path:</strong> <code>/api/v1/webhooks/whatsapp/ycloud</code></div>
                <div><strong>Auth Header:</strong> <code>X-API-Key</code></div>
                <div><strong>Signature Header:</strong> <code>YCloud-Signature</code></div>
              </div>
            </div>
          </div>

          {/* Connections List */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-gray-600" />
                <h2 className="text-lg font-semibold text-gray-900">
                  Configured WhatsApp Accounts
                </h2>
              </div>
              <button
                onClick={loadConnections}
                disabled={loading}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
                title="Refresh accounts"
              >
                <RefreshCw
                  className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
                />
              </button>
            </div>

            {loading ? (
              <div className="p-12 text-center text-gray-500">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-600" />
                Loading WhatsApp connections...
              </div>
            ) : connections.length === 0 ? (
              <div className="p-12 text-center">
                <Phone className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                <h3 className="text-sm font-medium text-gray-900">
                  No WhatsApp connections configured
                </h3>
                <p className="mt-1 text-sm text-gray-500">
                  Add your Meta Cloud API or YCloud credentials to begin sending and receiving messages.
                </p>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="mt-4 inline-flex items-center px-3.5 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700"
                >
                  <Plus className="w-4 h-4 mr-1.5" />
                  Configure Connection
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <th className="px-6 py-3">Account & Provider</th>
                      <th className="px-6 py-3">Identifiers</th>
                      <th className="px-6 py-3">Security & Status</th>
                      <th className="px-6 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {connections.map((conn) => (
                      <tr key={conn.id} className="hover:bg-gray-50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="font-medium text-gray-900">{conn.account_name}</div>
                          <div className="text-xs text-gray-500">{conn.display_phone_number}</div>
                          <span
                            className={`inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                              conn.provider === "meta"
                                ? "bg-blue-100 text-blue-800"
                                : "bg-emerald-100 text-emerald-800"
                            }`}
                          >
                            {conn.provider === "meta" ? "Meta Cloud API" : "YCloud API"}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-xs space-y-1 font-mono text-gray-600">
                          <div>Phone ID: {conn.phone_number_id}</div>
                          {conn.business_account_id && (
                            <div>WABA ID: {conn.business_account_id}</div>
                          )}
                        </td>
                        <td className="px-6 py-4 text-xs space-y-1.5">
                          <div className="flex items-center gap-1.5 text-emerald-700">
                            <Lock className="w-3.5 h-3.5" />
                            <span>Encrypted at rest (Fernet AES-128)</span>
                          </div>
                          <div>
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                conn.is_active
                                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                  : "bg-gray-100 text-gray-700"
                              }`}
                            >
                              {conn.is_active ? "Active" : "Inactive"}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-right space-x-2 text-xs">
                          <button
                            onClick={() => handleTestConnection(conn.id)}
                            disabled={testingId === conn.id}
                            className="inline-flex items-center px-2.5 py-1.5 border border-gray-300 rounded text-xs font-medium text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
                          >
                            {testingId === conn.id ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin mr-1" />
                            ) : (
                              <Server className="w-3.5 h-3.5 mr-1 text-blue-600" />
                            )}
                            Handshake
                          </button>
                          <button
                            onClick={() => {
                              setTestMsgModal({
                                id: conn.id,
                                phone: conn.display_phone_number,
                              });
                              setTestRecipient("");
                              setTestMsgResult(null);
                            }}
                            className="inline-flex items-center px-2.5 py-1.5 border border-gray-300 rounded text-xs font-medium text-gray-700 bg-white hover:bg-gray-50"
                          >
                            <Send className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                            Test Msg
                          </button>
                          <button
                            onClick={() => toggleConnectionStatus(conn, !conn.is_active)}
                            className="inline-flex items-center px-2.5 py-1.5 border border-transparent rounded text-xs font-medium text-gray-500 hover:text-gray-700"
                          >
                            {conn.is_active ? "Deactivate" : "Activate"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Handshake Result Display */}
          {testResult && (
            <div
              className={`rounded-xl border p-5 ${
                testResult.result.is_valid
                  ? "bg-emerald-50 border-emerald-200"
                  : "bg-red-50 border-red-200"
              }`}
            >
              <div className="flex items-start gap-3">
                {testResult.result.is_valid ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5 flex-shrink-0" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
                )}
                <div>
                  <h3
                    className={`text-sm font-semibold ${
                      testResult.result.is_valid
                        ? "text-emerald-900"
                        : "text-red-900"
                    }`}
                  >
                    Provider Handshake: {testResult.result.is_valid ? "VALID" : "FAILED"}
                  </h3>
                  <p
                    className={`text-sm mt-0.5 ${
                      testResult.result.is_valid
                        ? "text-emerald-700"
                        : "text-red-700"
                    }`}
                  >
                    {testResult.result.is_valid
                      ? `Successfully validated connection for ${testResult.result.display_name || "account"} (${testResult.result.phone_number || "verified"}).`
                      : `Validation error: ${testResult.result.error || "Unknown error"}`}
                  </p>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {/* TAB 2: LLM PROVIDERS */}
      {activeSettingsTab === "llm" && (
        <div className="space-y-6">
          <div className="bg-blue-50 border border-blue-200 p-4 rounded-xl text-sm text-blue-900">
            <strong>Physio One LLM Gateway:</strong> Unified multi-provider abstraction supporting Meta Model API (Muse),
            OpenAI, Anthropic, and generic OpenAI-compatible endpoints with token accounting and resilient fallback.
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {loadingLLM ? (
              <div className="col-span-full py-12 text-center text-gray-400">Loading LLM Providers...</div>
            ) : llmProviders.length === 0 ? (
              <div className="col-span-full py-12 text-center text-gray-400">No LLM providers configured.</div>
            ) : (
              llmProviders.map((p) => (
                <div key={p.id} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm flex flex-col justify-between">
                  <div>
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className="p-2 bg-indigo-50 text-indigo-700 rounded-lg">
                          <Cpu className="w-5 h-5" />
                        </div>
                        <div>
                          <h3 className="text-base font-semibold text-gray-900 uppercase tracking-wide">
                            {p.name}
                          </h3>
                          <span className="text-xs text-gray-500">{p.base_url}</span>
                        </div>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          p.is_enabled
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {p.is_enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>

                    <div className="space-y-2 bg-gray-50 p-3.5 rounded-lg border border-gray-100 text-xs text-gray-600 mb-4">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">API Key Status:</span>
                        <span className="font-mono text-gray-800 font-medium">
                          {p.masked_api_key}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">Health Diagnostics:</span>
                        <span className={`font-semibold capitalize ${p.health_status === 'healthy' ? 'text-emerald-700' : 'text-amber-700'}`}>
                          {p.health_status}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-500">Supported Models:</span>
                        <span className="text-gray-800">{p.models.length} registered</span>
                      </div>
                      {p.models.length > 0 && (
                        <div className="pt-1.5 border-t border-gray-200/60 flex flex-wrap gap-1">
                          {p.models.map((m) => (
                            <span key={m.id} className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-700 font-mono">
                              {m.model_identifier}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-gray-100 gap-2">
                    <button
                      onClick={() => handleTestLLMProvider(p.id)}
                      disabled={testingLlmId === p.id}
                      className="inline-flex items-center px-3 py-1.5 border border-indigo-200 rounded-lg text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50"
                    >
                      {testingLlmId === p.id ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin mr-1.5" />
                      ) : (
                        <Zap className="w-3.5 h-3.5 mr-1.5 text-indigo-600" />
                      )}
                      Test Connection
                    </button>
                    <button
                      onClick={() => openEditProvider(p)}
                      className="inline-flex items-center px-3 py-1.5 border border-gray-300 rounded-lg text-xs font-medium text-gray-700 bg-white hover:bg-gray-50"
                    >
                      <Sliders className="w-3.5 h-3.5 mr-1.5 text-gray-500" />
                      Configure
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* EDIT PROVIDER MODAL */}
      {editProviderModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-1">
              Configure {editProviderModal.name.toUpperCase()} Provider
            </h3>
            <p className="text-xs text-gray-500 mb-4">
              Credentials are encrypted using Fernet (AES-128-CBC) and never stored in plaintext.
            </p>

            <form onSubmit={handleSaveProvider} className="space-y-4 text-sm">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Base Endpoint URL</label>
                <input
                  type="text"
                  value={editProviderForm.base_url}
                  onChange={(e) => setEditProviderForm({ ...editProviderForm, base_url: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  API Key (Leave blank to keep existing key: {editProviderModal.masked_api_key})
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? "text" : "password"}
                    value={editProviderForm.api_key}
                    onChange={(e) => setEditProviderForm({ ...editProviderForm, api_key: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono pr-10"
                    placeholder="Enter new API key..."
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2.5 top-2 text-gray-400 hover:text-gray-600"
                  >
                    {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="providerActive"
                  checked={editProviderForm.is_enabled}
                  onChange={(e) => setEditProviderForm({ ...editProviderForm, is_enabled: e.target.checked })}
                  className="rounded text-blue-600"
                />
                <label htmlFor="providerActive" className="text-xs text-gray-700 cursor-pointer">
                  Provider Enabled for Agent Runtime & Fallbacks
                </label>
              </div>

              <div className="pt-4 flex justify-end gap-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setEditProviderModal(null)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingProvider}
                  className="px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
                >
                  {savingProvider ? "Saving..." : "Save Configuration"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}



      {/* ADD CONNECTION MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl max-w-lg w-full p-6 shadow-xl border border-gray-200">
            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
              <h3 className="text-lg font-bold text-gray-900">
                Configure WhatsApp Provider
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateConnection} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700 mb-1">
                  Provider Standard *
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setNewConn({ ...newConn, provider: "meta" })}
                    className={`p-3 rounded-lg border text-left flex flex-col justify-between ${
                      newConn.provider === "meta"
                        ? "border-blue-600 bg-blue-50 text-blue-900"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <span className="font-semibold text-sm">Meta Cloud API</span>
                    <span className="text-[11px] text-gray-500 mt-1">Official Graph API</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewConn({ ...newConn, provider: "ycloud" })}
                    className={`p-3 rounded-lg border text-left flex flex-col justify-between ${
                      newConn.provider === "ycloud"
                        ? "border-emerald-600 bg-emerald-50 text-emerald-900"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <span className="font-semibold text-sm">YCloud Provider</span>
                    <span className="text-[11px] text-gray-500 mt-1">Clinical Operations</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Account Name / Label *
                </label>
                <input
                  type="text"
                  value={newConn.account_name}
                  onChange={(e) =>
                    setNewConn({ ...newConn, account_name: e.target.value })
                  }
                  placeholder="e.g. Physio One Primary Support"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Display Phone Number *
                  </label>
                  <input
                    type="text"
                    value={newConn.display_phone_number}
                    onChange={(e) =>
                      setNewConn({ ...newConn, display_phone_number: e.target.value })
                    }
                    placeholder="+919876543210"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Phone Number ID *
                  </label>
                  <input
                    type="text"
                    value={newConn.phone_number_id}
                    onChange={(e) =>
                      setNewConn({ ...newConn, phone_number_id: e.target.value })
                    }
                    placeholder="e.g. 1029384756"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
                    required
                  />
                </div>
              </div>

              {newConn.provider === "meta" && (
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    WhatsApp Business Account ID (WABA)
                  </label>
                  <input
                    type="text"
                    value={newConn.business_account_id}
                    onChange={(e) =>
                      setNewConn({ ...newConn, business_account_id: e.target.value })
                    }
                    placeholder="e.g. 9876543210"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Webhook Verify Token *
                </label>
                <input
                  type="text"
                  value={newConn.webhook_verify_token}
                  onChange={(e) =>
                    setNewConn({ ...newConn, webhook_verify_token: e.target.value })
                  }
                  placeholder="Custom alphanumeric verification token"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Access Token / API Key *
                </label>
                <input
                  type="password"
                  value={newConn.access_token}
                  onChange={(e) =>
                    setNewConn({ ...newConn, access_token: e.target.value })
                  }
                  placeholder="Encrypted symmetrically with Fernet"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  App Secret / Webhook Secret Key
                </label>
                <input
                  type="password"
                  value={newConn.secret_key}
                  onChange={(e) =>
                    setNewConn({ ...newConn, secret_key: e.target.value })
                  }
                  placeholder="Used for HMAC-SHA256 signature verification"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
                />
              </div>

              <div className="pt-4 flex justify-end gap-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingConnection}
                  className="px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
                >
                  {savingConnection ? "Saving..." : "Save Connection"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* SEND TEST MESSAGE MODAL */}
      {testMsgModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-gray-200">
            <h3 className="text-lg font-bold text-gray-900 mb-1">
              Dispatch Test WhatsApp Message
            </h3>
            <p className="text-xs text-gray-500 mb-4">
              Dispatches an isolated test message from {testMsgModal.phone} to verify outbound routing.
            </p>

            <form onSubmit={handleSendTestMessage} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Recipient Phone Number *
                </label>
                <input
                  type="text"
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                  placeholder="e.g. +919876543210"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Message Body
                </label>
                <textarea
                  value={testMessageText}
                  onChange={(e) => setTestMessageText(e.target.value)}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  required
                />
              </div>

              {testMsgResult && (
                <div
                  className={`p-3 rounded-lg text-xs border ${
                    testMsgResult.status === "sent"
                      ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                      : "bg-red-50 border-red-200 text-red-800"
                  }`}
                >
                  <div className="font-semibold">
                    Status: {testMsgResult.status.toUpperCase()}
                  </div>
                  <div>Message ID: {testMsgResult.provider_message_id}</div>
                </div>
              )}

              <div className="pt-4 flex justify-end gap-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => {
                    setTestMsgModal(null);
                    setTestMsgResult(null);
                  }}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={sendingTestMsg}
                  className="px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                >
                  {sendingTestMsg ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    <>
                      <Send className="w-4 h-4" />
                      Send Test
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
