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
} from "lucide-react";
import {
  apiClient,
  WhatsAppConnection,
  ConnectionTestResult,
  TestMessageResult,
} from "@/lib/api-client";

export default function SettingsPage() {
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

  useEffect(() => {
    loadConnections();
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
      setActionSuccess("WhatsApp connection successfully configured.");
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
    setTestMsgResult(null);
    try {
      const res = await apiClient.sendWhatsAppTestMessage(testMsgModal.id, {
        recipient_phone: testRecipient,
        message_text: testMessageText,
      });
      setTestMsgResult(res);
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

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-gray-200">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900">
            System Settings & WhatsApp Integrations
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure WhatsApp Cloud API and YCloud connections for Physio One.
            All credentials are symmetrically encrypted using Fernet (AES-128-CBC + HMAC-SHA256).
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Connection
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
              <tbody className="divide-y divide-gray-200 text-sm">
                {connections.map((conn) => (
                  <tr key={conn.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-semibold text-gray-900 flex items-center gap-2">
                        <Phone className="w-4 h-4 text-gray-400" />
                        {conn.display_phone_number}
                      </div>
                      <div className="text-xs text-gray-500">{conn.account_name}</div>
                      <div className="mt-1">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            conn.provider === "meta"
                              ? "bg-blue-100 text-blue-800"
                              : "bg-emerald-100 text-emerald-800"
                          }`}
                        >
                          {conn.provider === "meta"
                            ? "Meta Cloud API"
                            : "YCloud API"}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 space-y-1 text-xs text-gray-600">
                      <div>
                        <span className="text-gray-400">Phone ID:</span>{" "}
                        <code>{conn.phone_number_id || "N/A"}</code>
                      </div>
                      <div>
                        <span className="text-gray-400">WABA ID:</span>{" "}
                        <code>{conn.business_account_id || "N/A"}</code>
                      </div>
                    </td>
                    <td className="px-6 py-4 space-y-1">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            conn.is_active
                              ? "bg-emerald-100 text-emerald-800"
                              : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {conn.is_active ? "Active" : "Inactive"}
                        </span>
                        <button
                          onClick={() =>
                            toggleConnectionStatus(conn, !conn.is_active)
                          }
                          className="text-xs text-blue-600 hover:underline ml-1"
                        >
                          {conn.is_active ? "Deactivate" : "Activate"}
                        </button>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-emerald-700">
                        <Lock className="w-3 h-3" />
                        <span>Encrypted at rest (Fernet AES-128)</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right space-x-2 whitespace-nowrap">
                      <button
                        onClick={() => handleTestConnection(conn.id)}
                        disabled={testingId === conn.id}
                        className="inline-flex items-center px-2.5 py-1.5 border border-gray-300 rounded-lg text-xs font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 disabled:opacity-50"
                      >
                        <RefreshCw
                          className={`w-3.5 h-3.5 mr-1 ${
                            testingId === conn.id ? "animate-spin" : ""
                          }`}
                        />
                        Handshake
                      </button>
                      <button
                        onClick={() =>
                          setTestMsgModal({
                            id: conn.id,
                            phone: conn.display_phone_number,
                          })
                        }
                        className="inline-flex items-center px-2.5 py-1.5 border border-blue-600 rounded-lg text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500"
                      >
                        <Send className="w-3.5 h-3.5 mr-1" />
                        Send Test
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
                  ? `Successfully validated connection for ${testResult.result.display_name || 'account'} (${testResult.result.phone_number || 'verified'}).`
                  : `Validation error: ${testResult.result.error || 'Unknown error'}`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Add WhatsApp Connection */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-gray-100">
            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">
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
                <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                  Provider Implementation
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() =>
                      setNewConn({ ...newConn, provider: "meta" })
                    }
                    className={`py-2 px-3 border rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-colors ${
                      newConn.provider === "meta"
                        ? "border-blue-600 bg-blue-50 text-blue-700"
                        : "border-gray-200 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    Meta Cloud API
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setNewConn({ ...newConn, provider: "ycloud" })
                    }
                    className={`py-2 px-3 border rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-colors ${
                      newConn.provider === "ycloud"
                        ? "border-emerald-600 bg-emerald-50 text-emerald-700"
                        : "border-gray-200 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    YCloud Provider
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Account Name / Label
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Physio One Main Support"
                  value={newConn.account_name}
                  onChange={(e) =>
                    setNewConn({ ...newConn, account_name: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Display Phone Number (E.164 format)
                </label>
                <input
                  type="text"
                  required
                  placeholder="+919876543210"
                  value={newConn.display_phone_number}
                  onChange={(e) =>
                    setNewConn({ ...newConn, display_phone_number: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Phone Number ID
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. 1092837465..."
                    value={newConn.phone_number_id}
                    onChange={(e) =>
                      setNewConn({
                        ...newConn,
                        phone_number_id: e.target.value,
                      })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Business Account ID (WABA)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 987654321..."
                    value={newConn.business_account_id}
                    onChange={(e) =>
                      setNewConn({
                        ...newConn,
                        business_account_id: e.target.value,
                      })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Webhook Verify Token
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    required
                    placeholder="Custom alphanumeric verification token"
                    value={newConn.webhook_verify_token}
                    onChange={(e) =>
                      setNewConn({
                        ...newConn,
                        webhook_verify_token: e.target.value,
                      })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setNewConn({
                        ...newConn,
                        webhook_verify_token:
                          "whsec_" + Math.random().toString(36).substring(2, 15),
                      })
                    }
                    className="px-3 py-2 border border-gray-300 text-xs text-gray-700 rounded-lg hover:bg-gray-50"
                  >
                    Generate
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Access Token / API Key (Encrypted at rest)
                </label>
                <input
                  type="password"
                  required
                  placeholder="EAAG... or YCloud API Key"
                  value={newConn.access_token}
                  onChange={(e) =>
                    setNewConn({ ...newConn, access_token: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  App Secret / Webhook Secret (Encrypted at rest)
                </label>
                <input
                  type="password"
                  placeholder="Meta App Secret or YCloud Signing Secret"
                  value={newConn.secret_key}
                  onChange={(e) =>
                    setNewConn({ ...newConn, secret_key: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
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
                  className="px-4 py-2 border border-transparent rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
                >
                  {savingConnection ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Save Connection"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Send Test Message */}
      {testMsgModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-gray-100">
            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
              <h3 className="text-lg font-semibold text-gray-900">
                Send Test WhatsApp Message
              </h3>
              <button
                onClick={() => {
                  setTestMsgModal(null);
                  setTestMsgResult(null);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSendTestMessage} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Sender Account
                </label>
                <input
                  type="text"
                  disabled
                  value={testMsgModal.phone}
                  className="w-full px-3 py-2 border border-gray-200 bg-gray-50 rounded-lg text-sm text-gray-600"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Recipient Phone (E.164 format)
                </label>
                <input
                  type="text"
                  required
                  placeholder="+919876543210"
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Message Body
                </label>
                <textarea
                  required
                  rows={3}
                  value={testMessageText}
                  onChange={(e) => setTestMessageText(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
