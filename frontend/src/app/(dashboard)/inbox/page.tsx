'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import {
  MessageSquare,
  Search,
  Send,
  UserCheck,
  Bot,
  PauseCircle,
  PlayCircle,
  Settings,
  AlertTriangle,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  Phone,
  ShieldAlert,
} from 'lucide-react';
import {
  apiClient,
  ConversationListItem,
  ConversationDetail,
  ConversationMessage,
  AIInboundSettings,
} from '@/lib/api-client';

export default function InboxPage() {
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(null);
  const [search, setSearch] = useState('');
  const [filterTakeover, setFilterTakeover] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [takeoverOnReply, setTakeoverOnReply] = useState(true);

  // Settings Modal State
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [settings, setSettings] = useState<AIInboundSettings | null>(null);
  const [selectedMode, setSelectedMode] = useState<'disabled' | 'shadow' | 'live'>('disabled');
  const [debounceSec, setDebounceSec] = useState<number>(5);
  const [savingSettings, setSavingSettings] = useState(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  const fetchConversations = useCallback(async () => {
    try {
      setErrorBanner(null);
      const list = await apiClient.getConversations({
        takeover_only: filterTakeover,
        search: search.trim() || undefined,
      });
      setConversations(list);
      if (list.length > 0 && !selectedId) {
        setSelectedId(list[0].id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load conversations';
      setErrorBanner(msg);
    } finally {
      setLoading(false);
    }
  }, [filterTakeover, search, selectedId]);

  const fetchConversationDetail = useCallback(async (id: string) => {
    try {
      setDetailLoading(true);
      const detail = await apiClient.getConversationDetail(id);
      setActiveConversation(detail);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load conversation details';
      setErrorBanner(msg);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const s = await apiClient.getAiInboundSettings();
      setSettings(s);
      setSelectedMode(s.ai_mode);
      setDebounceSec(s.debounce_seconds);
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  }, []);

  useEffect(() => {
    fetchConversations();
    fetchSettings();
  }, [fetchConversations, fetchSettings]);

  useEffect(() => {
    if (selectedId) {
      fetchConversationDetail(selectedId);
    }
  }, [selectedId, fetchConversationDetail]);

  const handleSendReply = async () => {
    if (!selectedId || !replyText.trim() || sending) return;
    try {
      setSending(true);
      setErrorBanner(null);
      await apiClient.sendConversationReply(selectedId, {
        message: replyText.trim(),
        takeover: takeoverOnReply,
      });
      setReplyText('');
      setSuccessBanner('Reply sent successfully');
      await fetchConversationDetail(selectedId);
      await fetchConversations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send reply';
      setErrorBanner(msg);
    } finally {
      setSending(false);
    }
  };

  const handleTakeover = async () => {
    if (!selectedId) return;
    try {
      await apiClient.takeoverConversation(selectedId, 'Manual staff takeover');
      setSuccessBanner('Human staff takeover enabled');
      await fetchConversationDetail(selectedId);
      await fetchConversations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Takeover failed';
      setErrorBanner(msg);
    }
  };

  const handleResumeAI = async () => {
    if (!selectedId) return;
    try {
      await apiClient.resumeAiConversation(selectedId);
      setSuccessBanner('AI Receptionist responses resumed');
      await fetchConversationDetail(selectedId);
      await fetchConversations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Resume failed';
      setErrorBanner(msg);
    }
  };

  const handlePauseAI = async () => {
    if (!selectedId) return;
    try {
      await apiClient.pauseAiConversation(selectedId, 'Staff paused AI');
      setSuccessBanner('AI paused for this conversation');
      await fetchConversationDetail(selectedId);
      await fetchConversations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Pause failed';
      setErrorBanner(msg);
    }
  };

  const handleSaveSettings = async () => {
    try {
      setSavingSettings(true);
      setErrorBanner(null);
      const updated = await apiClient.updateAiInboundSettings({
        ai_mode: selectedMode,
        debounce_seconds: Number(debounceSec),
      });
      setSettings(updated);
      setSuccessBanner(`AI Orchestration set to '${updated.ai_mode.toUpperCase()}' mode`);
      setShowSettingsModal(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update settings';
      setErrorBanner(msg);
    } finally {
      setSavingSettings(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Live WhatsApp Inbox</h1>
          <p className="text-sm text-slate-500">
            Real-time conversations, Deepti AI receptionist orchestration, and safety takeovers.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {settings && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-slate-200 bg-white text-xs shadow-sm">
              <span className="font-semibold text-slate-700">AI Mode:</span>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                  settings.ai_mode === 'live'
                    ? 'bg-emerald-100 text-emerald-800'
                    : settings.ai_mode === 'shadow'
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-slate-100 text-slate-800'
                }`}
                data-testid="ai-mode-badge"
              >
                {settings.ai_mode.toUpperCase()}
              </span>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowSettingsModal(true)}
            className="flex items-center gap-1.5 text-xs"
          >
            <Settings className="h-4 w-4 text-slate-600" />
            AI Settings
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              fetchConversations();
              if (selectedId) fetchConversationDetail(selectedId);
            }}
            className="flex items-center gap-1.5 text-xs"
          >
            <RefreshCw className="h-4 w-4 text-slate-600" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {errorBanner && (
        <Alert variant="destructive" title="Error">
          <div className="flex items-center justify-between">
            <span>{errorBanner}</span>
            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              className="ml-4 font-bold text-xs opacity-75 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        </Alert>
      )}
      {successBanner && (
        <Alert variant="success" title="Success">
          <div className="flex items-center justify-between">
            <span>{successBanner}</span>
            <button
              type="button"
              onClick={() => setSuccessBanner(null)}
              className="ml-4 font-bold text-xs opacity-75 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        </Alert>
      )}

      {/* Main Split Interface */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-220px)] min-h-[500px]">
        {/* Left Column: Conversations List */}
        <Card className="lg:col-span-4 flex flex-col h-full overflow-hidden border-slate-200 shadow-sm">
          <CardHeader className="p-4 border-b border-slate-100 space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search phone or name..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9 text-xs"
              />
            </div>
            <div className="flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={() => setFilterTakeover(false)}
                className={`px-3 py-1 rounded-md transition font-medium ${
                  !filterTakeover ? 'bg-teal-50 text-teal-700' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                All Chats
              </button>
              <button
                type="button"
                onClick={() => setFilterTakeover(true)}
                className={`px-3 py-1 rounded-md transition font-medium ${
                  filterTakeover ? 'bg-amber-50 text-amber-700' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                Human Takeover
              </button>
            </div>
          </CardHeader>

          <CardContent className="p-0 flex-1 overflow-y-auto divide-y divide-slate-100">
            {loading ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading chats...</div>
            ) : conversations.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">
                <MessageSquare className="h-8 w-8 mx-auto text-slate-300 mb-2" />
                No conversations found.
              </div>
            ) : (
              conversations.map((conv) => {
                const isSelected = conv.id === selectedId;
                return (
                  <div
                    key={conv.id}
                    onClick={() => setSelectedId(conv.id)}
                    className={`p-3.5 cursor-pointer transition flex flex-col gap-1.5 ${
                      isSelected ? 'bg-teal-50/60 border-l-4 border-teal-600' : 'hover:bg-slate-50'
                    }`}
                    data-testid={`conversation-item-${conv.id}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs text-slate-900 truncate">
                        {conv.contact_name || conv.contact_phone}
                      </span>
                      {conv.last_message_at && (
                        <span className="text-[10px] text-slate-400">
                          {new Date(conv.last_message_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>

                    <p className="text-xs text-slate-500 truncate">
                      {conv.last_message_body || 'No messages yet'}
                    </p>

                    <div className="flex items-center gap-1.5 pt-1">
                      {conv.is_human_takeover && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded">
                          <UserCheck className="h-3 w-3" /> Staff
                        </span>
                      )}
                      {conv.ai_paused && !conv.is_human_takeover && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-purple-800 bg-purple-100 px-1.5 py-0.5 rounded">
                          <PauseCircle className="h-3 w-3" /> AI Paused
                        </span>
                      )}
                      {!conv.is_human_takeover && !conv.ai_paused && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-teal-800 bg-teal-100 px-1.5 py-0.5 rounded">
                          <Bot className="h-3 w-3" /> Deepti Active
                        </span>
                      )}
                      {conv.opted_out && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-red-800 bg-red-100 px-1.5 py-0.5 rounded">
                          <ShieldAlert className="h-3 w-3" /> Opted Out
                        </span>
                      )}
                      {conv.pending_draft_count > 0 && (
                        <span className="text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                          {conv.pending_draft_count} Draft
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        {/* Right Column: Chat History & Action Control */}
        <Card className="lg:col-span-8 flex flex-col h-full overflow-hidden border-slate-200 shadow-sm">
          {activeConversation ? (
            <>
              {/* Conversation Top Action Bar */}
              <div className="p-4 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 bg-white">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center font-bold text-sm">
                    {(activeConversation.contact_name || activeConversation.contact_phone).substring(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <h2 className="font-semibold text-sm text-slate-900">
                      {activeConversation.contact_name || 'Patient'}
                    </h2>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      <Phone className="h-3 w-3" />
                      <span>{activeConversation.contact_phone}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {activeConversation.is_human_takeover ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleResumeAI}
                      className="text-xs border-teal-300 text-teal-700 hover:bg-teal-50 flex items-center gap-1"
                    >
                      <PlayCircle className="h-3.5 w-3.5 text-teal-600" />
                      Resume AI
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleTakeover}
                        className="text-xs border-amber-300 text-amber-700 hover:bg-amber-50 flex items-center gap-1"
                      >
                        <UserCheck className="h-3.5 w-3.5 text-amber-600" />
                        Take Over
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handlePauseAI}
                        className="text-xs border-purple-300 text-purple-700 hover:bg-purple-50 flex items-center gap-1"
                      >
                        <PauseCircle className="h-3.5 w-3.5 text-purple-600" />
                        Pause AI
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {/* Message Timeline */}
              <div className="flex-1 p-4 overflow-y-auto space-y-3 bg-slate-50/50">
                {detailLoading ? (
                  <div className="py-12 text-center text-xs text-slate-400">Loading messages...</div>
                ) : activeConversation.messages.length === 0 ? (
                  <div className="py-12 text-center text-xs text-slate-400">
                    No messages in this conversation.
                  </div>
                ) : (
                  activeConversation.messages.map((msg) => {
                    const isInbound = msg.direction === 'inbound';
                    return (
                      <div
                        key={msg.id}
                        className={`flex flex-col ${isInbound ? 'items-start' : 'items-end'}`}
                      >
                        <div
                          className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-xs shadow-sm ${
                            isInbound
                              ? 'bg-white text-slate-900 border border-slate-200'
                              : 'bg-teal-600 text-white'
                          }`}
                        >
                          <p className="whitespace-pre-wrap">{msg.body}</p>
                        </div>
                        <span className="text-[10px] text-slate-400 mt-1 px-1">
                          {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          {' • '}
                          {isInbound ? 'Patient' : 'Staff/AI'}
                        </span>
                      </div>
                    );
                  })
                )}

                {/* AI Drafts Card (Shadow Mode) */}
                {activeConversation.drafts && activeConversation.drafts.length > 0 && (
                  <div className="my-4 border border-amber-200 bg-amber-50/70 rounded-xl p-3.5 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-900">
                        <Bot className="h-4 w-4 text-amber-600" />
                        Deepti AI Draft ({activeConversation.drafts[0].ai_mode.toUpperCase()} Mode)
                      </span>
                      <span className="text-[10px] text-amber-700">
                        {activeConversation.drafts[0].dispatched ? 'Dispatched' : 'Pending Staff Review'}
                      </span>
                    </div>
                    <p className="text-xs text-amber-950 bg-white p-2.5 rounded-lg border border-amber-200 whitespace-pre-wrap">
                      {activeConversation.drafts[0].draft_text}
                    </p>
                    {!activeConversation.drafts[0].dispatched && (
                      <div className="flex justify-end">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setReplyText(activeConversation.drafts[0].draft_text)}
                          className="text-xs border-amber-300 text-amber-800 hover:bg-amber-100"
                        >
                          Use this Draft
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Bottom Reply Bar */}
              <div className="p-3 bg-white border-t border-slate-200 space-y-2">
                {activeConversation.opted_out ? (
                  <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-800 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-600 flex-shrink-0" />
                    <span>Patient has opted out of messages. Outbound communications are disabled.</span>
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder="Type manual reply to patient..."
                        value={replyText}
                        onChange={(e) => setReplyText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSendReply();
                          }
                        }}
                        className="text-xs"
                        disabled={sending}
                      />
                      <Button
                        size="sm"
                        onClick={handleSendReply}
                        disabled={!replyText.trim() || sending}
                        className="bg-teal-600 hover:bg-teal-700 text-white flex items-center gap-1.5 text-xs"
                      >
                        <Send className="h-3.5 w-3.5" />
                        Send
                      </Button>
                    </div>

                    <div className="flex items-center justify-between text-xs text-slate-500 px-1">
                      <label className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={takeoverOnReply}
                          onChange={(e) => setTakeoverOnReply(e.target.checked)}
                          className="rounded border-slate-300 text-teal-600 focus:ring-teal-500 h-3.5 w-3.5"
                        />
                        <span>Enable human takeover on reply</span>
                      </label>
                      <span className="text-[10px] text-slate-400">Press Enter to send</span>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center p-8 space-y-3 text-slate-400">
              <MessageSquare className="h-12 w-12 text-slate-300" />
              <p className="text-sm">Select a conversation from the left to view messages.</p>
            </div>
          )}
        </Card>
      </div>

      {/* AI Orchestration Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl max-w-md w-full shadow-xl border border-slate-200 overflow-hidden">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Bot className="h-5 w-5 text-teal-600" />
                <h3 className="font-semibold text-sm text-slate-900">AI Receptionist Settings</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowSettingsModal(false)}
                className="text-slate-400 hover:text-slate-600 text-sm"
              >
                ✕
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              <Alert variant="warning" title="Safety Policy Enforcement">
                AI Mode defaults strictly to <strong>DISABLED</strong>. Both Shadow and Live modes require explicit administrative authorization.
              </Alert>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-700 block">AI Operating Mode</label>
                <div className="grid grid-cols-3 gap-2">
                  {(['disabled', 'shadow', 'live'] as const).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setSelectedMode(mode)}
                      className={`p-2.5 rounded-lg border text-center transition font-semibold capitalize ${
                        selectedMode === mode
                          ? mode === 'live'
                            ? 'border-emerald-600 bg-emerald-50 text-emerald-800'
                            : mode === 'shadow'
                            ? 'border-amber-600 bg-amber-50 text-amber-800'
                            : 'border-slate-600 bg-slate-100 text-slate-900'
                          : 'border-slate-200 hover:bg-slate-50 text-slate-600'
                      }`}
                      data-testid={`mode-btn-${mode}`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
                <p className="text-[11px] text-slate-500 pt-1">
                  {selectedMode === 'disabled' && 'AI responses and drafting are completely deactivated.'}
                  {selectedMode === 'shadow' && 'Generates AI drafts for staff review in inbox without sending to WhatsApp.'}
                  {selectedMode === 'live' && 'Autonomously dispatches replies to WhatsApp patients within strict safety guardrails.'}
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="font-semibold text-slate-700 block">Message Debounce Window (Seconds)</label>
                <Input
                  type="number"
                  min="1"
                  max="60"
                  value={debounceSec}
                  onChange={(e) => setDebounceSec(Number(e.target.value))}
                  className="text-xs"
                />
                <p className="text-[11px] text-slate-500">
                  Aggregates rapid burst messages into a single conversational turn (default: 5 seconds).
                </p>
              </div>
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowSettingsModal(false)}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSaveSettings}
                disabled={savingSettings}
                className="bg-teal-600 hover:bg-teal-700 text-white text-xs"
              >
                {savingSettings ? 'Saving...' : 'Save Configuration'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
