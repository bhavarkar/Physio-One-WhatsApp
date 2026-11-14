import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import InboxPage from './page';
import { apiClient } from '@/lib/api-client';

const mockConversations = [
  {
    id: 'conv-1',
    contact_id: 'contact-1',
    contact_name: 'Rahul Sharma',
    contact_phone: '+919876543210',
    status: 'open',
    is_human_takeover: false,
    ai_paused: false,
    opted_out: false,
    last_message_at: new Date().toISOString(),
    last_message_body: 'Can I check consultation slots for Wednesday?',
    last_message_direction: 'inbound',
    unread_count: 1,
    pending_draft_count: 1,
    created_at: new Date().toISOString(),
  },
  {
    id: 'conv-2',
    contact_id: 'contact-2',
    contact_name: 'Priya Verma',
    contact_phone: '+919876543211',
    status: 'open',
    is_human_takeover: true,
    ai_paused: false,
    opted_out: false,
    last_message_at: new Date().toISOString(),
    last_message_body: 'Thank you doctor, will come tomorrow.',
    last_message_direction: 'outbound',
    unread_count: 0,
    pending_draft_count: 0,
    created_at: new Date().toISOString(),
  },
  {
    id: 'conv-3',
    contact_id: 'contact-3',
    contact_name: 'Anil Kumar',
    contact_phone: '+919876543212',
    status: 'open',
    is_human_takeover: false,
    ai_paused: false,
    opted_out: true,
    last_message_at: new Date().toISOString(),
    last_message_body: 'STOP',
    last_message_direction: 'inbound',
    unread_count: 0,
    pending_draft_count: 0,
    created_at: new Date().toISOString(),
  },
];

const mockDetailConv1 = {
  id: 'conv-1',
  contact_id: 'contact-1',
  contact_name: 'Rahul Sharma',
  contact_phone: '+919876543210',
  status: 'open',
  is_human_takeover: false,
  ai_paused: false,
  opted_out: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  messages: [
    {
      id: 'msg-1',
      provider: 'meta',
      direction: 'inbound' as const,
      message_type: 'text',
      body: 'Can I check consultation slots for Wednesday?',
      media_url: null,
      media_mime_type: null,
      status: 'received',
      error_message: null,
      created_at: new Date().toISOString(),
    },
  ],
  drafts: [
    {
      id: 'draft-1',
      conversation_id: 'conv-1',
      session_id: 'sess-1',
      agent_id: 'agent-1',
      inbound_job_id: 'job-1',
      aggregated_inbound_text: 'Can I check consultation slots for Wednesday?',
      draft_text: 'Hello Rahul! Physio One has available slots on Wednesday between 9:00 AM and 8:00 PM IST.',
      ai_mode: 'shadow',
      dispatched: false,
      outbound_message_id: null,
      created_at: new Date().toISOString(),
    },
  ],
  handoffs: [],
};

const mockSettings = {
  id: 'settings-1',
  account_id: null,
  ai_mode: 'disabled' as const,
  active_agent_id: null,
  active_agent_name: 'Deepti',
  debounce_seconds: 5,
  max_ai_steps: 5,
  processing_timeout_seconds: 60,
  opt_out_keywords: ['stop', 'unsubscribe'],
  emergency_keywords: ['emergency', 'severe pain'],
  is_active: true,
  updated_at: new Date().toISOString(),
};

describe('InboxPage (WhatsApp Live Inbox & AI Receptionist Orchestration)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(apiClient, 'getConversations').mockResolvedValue(mockConversations);
    jest.spyOn(apiClient, 'getConversationDetail').mockResolvedValue(mockDetailConv1);
    jest.spyOn(apiClient, 'getAiInboundSettings').mockResolvedValue(mockSettings);
    jest.spyOn(apiClient, 'sendConversationReply').mockResolvedValue({
      id: 'msg-sent-1',
      provider: 'meta',
      direction: 'outbound',
      message_type: 'text',
      body: 'Sure, we can book 10:00 AM for you.',
      media_url: null,
      media_mime_type: null,
      status: 'sent',
      error_message: null,
      created_at: new Date().toISOString(),
    });
    jest.spyOn(apiClient, 'takeoverConversation').mockResolvedValue({
      status: 'success',
      is_human_takeover: true,
      message: 'Human takeover enabled',
    });
    jest.spyOn(apiClient, 'resumeAiConversation').mockResolvedValue({
      status: 'success',
      is_human_takeover: false,
      ai_paused: false,
      message: 'AI responses resumed',
    });
    jest.spyOn(apiClient, 'pauseAiConversation').mockResolvedValue({
      status: 'success',
      ai_paused: true,
      message: 'AI paused',
    });
    jest.spyOn(apiClient, 'updateAiInboundSettings').mockResolvedValue({
      ...mockSettings,
      ai_mode: 'shadow',
    });
  });

  test('renders live inbox with conversation list and default disabled AI mode badge', async () => {
    render(<InboxPage />);

    expect(screen.getByText('Live WhatsApp Inbox')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Rahul Sharma')).toBeInTheDocument();
      expect(screen.getByText('Priya Verma')).toBeInTheDocument();
    });

    const badge = screen.getByTestId('ai-mode-badge');
    expect(badge).toHaveTextContent('DISABLED');
  });

  test('displays conversation messages, timeline, and AI draft in shadow mode', async () => {
    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('Can I check consultation slots for Wednesday?')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Deepti AI Draft \(SHADOW Mode\)/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Hello Rahul! Physio One has available slots/i)).toBeInTheDocument();

    // Clicking "Use this Draft" copies text into reply box
    const useDraftBtn = screen.getByText('Use this Draft');
    fireEvent.click(useDraftBtn);

    const input = await screen.findByPlaceholderText('Type manual reply to patient...');
    expect(input).toHaveValue('Hello Rahul! Physio One has available slots on Wednesday between 9:00 AM and 8:00 PM IST.');
  });

  test('sends manual staff reply and refreshes conversation timeline', async () => {
    render(<InboxPage />);

    const input = await screen.findByPlaceholderText('Type manual reply to patient...');
    fireEvent.change(input, { target: { value: 'Sure, we can book 10:00 AM for you.' } });

    const sendBtn = screen.getByRole('button', { name: /send/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(apiClient.sendConversationReply).toHaveBeenCalledWith('conv-1', {
        message: 'Sure, we can book 10:00 AM for you.',
        takeover: true,
      });
    });
  });

  test('handles human staff takeover and pause toggles', async () => {
    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('Take Over')).toBeInTheDocument();
    });

    const takeoverBtn = screen.getByText('Take Over');
    fireEvent.click(takeoverBtn);

    await waitFor(() => {
      expect(apiClient.takeoverConversation).toHaveBeenCalledWith('conv-1', 'Manual staff takeover');
    });

    const pauseBtn = screen.getByText('Pause AI');
    fireEvent.click(pauseBtn);

    await waitFor(() => {
      expect(apiClient.pauseAiConversation).toHaveBeenCalledWith('conv-1', 'Staff paused AI');
    });
  });

  test('updates AI inbound settings modal and changes mode to shadow', async () => {
    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('AI Settings')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('AI Settings'));

    expect(screen.getByText('AI Receptionist Settings')).toBeInTheDocument();
    expect(screen.getByText(/AI Mode defaults strictly to/i)).toBeInTheDocument();

    // Select shadow mode
    const shadowBtn = screen.getByTestId('mode-btn-shadow');
    fireEvent.click(shadowBtn);

    const saveBtn = screen.getByText('Save Configuration');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(apiClient.updateAiInboundSettings).toHaveBeenCalledWith({
        ai_mode: 'shadow',
        debounce_seconds: 5,
      });
    });
  });

  test('disables outbound reply when patient has opted out', async () => {
    jest.spyOn(apiClient, 'getConversationDetail').mockImplementation((id: string) => {
      if (id === 'conv-3') {
        return Promise.resolve({
          ...mockDetailConv1,
          id: 'conv-3',
          opted_out: true,
        });
      }
      return Promise.resolve(mockDetailConv1);
    });

    render(<InboxPage />);

    await waitFor(() => {
      expect(screen.getByText('Anil Kumar')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Anil Kumar'));

    await waitFor(() => {
      expect(screen.getByText(/Patient has opted out of messages. Outbound communications are disabled/i)).toBeInTheDocument();
    });

    expect(screen.queryByPlaceholderText('Type manual reply to patient...')).not.toBeInTheDocument();
  });
});
