import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AgentsPage from './page';
import { apiClient } from '@/lib/api-client';

const mockAgent = {
  id: 'agent-deepti-1',
  name: 'Deepti',
  description: 'AI Receptionist for Physio One Clinic.',
  is_active: true,
  current_version: 1,
  primary_model_id: 'model-muse-1',
  primary_model_identifier: 'muse-v1',
  fallback_model_id: null,
  fallback_model_identifier: null,
  temperature: 0.2,
  max_tokens: 1024,
  context_window_tokens: 8192,
  max_execution_steps: 5,
  execution_timeout_seconds: 30,
  system_prompt: 'You are Deepti, the front-desk clinic receptionist for Physio One.',
  allowed_tools: ['check_availability', 'find_patient'],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockModel = {
  id: 'model-muse-1',
  provider_id: 'prov-muse-1',
  provider_name: 'muse',
  model_identifier: 'muse-v1',
  display_name: 'Muse v1 Clinical',
  context_window_tokens: 8192,
  max_output_tokens: 2048,
  supports_tools: false,
  supports_streaming: false,
  supports_structured_output: false,
  input_token_cost_per_million: 0.5,
  output_token_cost_per_million: 1.5,
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockTool = {
  name: 'check_availability',
  description: 'Check available appointment slots for a given practitioner and date.',
  category: 'clinical',
  is_mutation: false,
  parameters: { type: 'object', properties: { date: { type: 'string' } } },
};

describe('AgentsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    jest.spyOn(apiClient, 'getAgents').mockResolvedValue([mockAgent]);
    jest.spyOn(apiClient, 'getLLMModels').mockResolvedValue([mockModel]);
    jest.spyOn(apiClient, 'getTools').mockResolvedValue([mockTool]);
  });

  it('renders agent management header and lists Deepti agent card', async () => {
    render(<AgentsPage />);

    expect(screen.getByText(/AI Agents & Receptionist Runtime/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Deepti')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText(/AI Receptionist for Physio One Clinic/i)).toBeInTheDocument();
    });
  });

  it('opens isolated test console, executes test message, and displays latency and response', async () => {
    jest.spyOn(apiClient, 'testAgent').mockResolvedValue({
      session_id: 'session-test-123',
      agent_id: mockAgent.id,
      agent_version: 1,
      provider: 'muse',
      model: 'muse-v1',
      status: 'completed',
      total_execution_steps: 1,
      total_input_tokens: 42,
      total_output_tokens: 28,
      duration_ms: 350,
      response_text: 'Hello! I am Deepti. Physio One is open Monday through Saturday.',
      tool_calls: [],
      error_message: null,
    });

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('Deepti')).toBeInTheDocument();
    });

    // Click "Test" button
    fireEvent.click(screen.getByRole('button', { name: /Test/i }));

    // Verify modal appears
    await waitFor(() => {
      expect(screen.getByText(/Isolated Test Console — Deepti/i)).toBeInTheDocument();
    });

    // Enter test prompt
    const input = screen.getByPlaceholderText(/Type a clinical inquiry or availability question/i);
    fireEvent.change(input, { target: { value: 'What are your hours?' } });

    // Click "Send Test"
    fireEvent.click(screen.getByRole('button', { name: /Send Test/i }));

    // Verify response
    await waitFor(() => {
      expect(screen.getByText(/Hello! I am Deepti. Physio One is open Monday through Saturday./i)).toBeInTheDocument();
      expect(screen.getByText('350ms')).toBeInTheDocument();
      expect(screen.getByText('42 / 28')).toBeInTheDocument();
    });
  });

  it('opens version history dialog and displays version snapshots', async () => {
    jest.spyOn(apiClient, 'getAgentVersions').mockResolvedValue([
      {
        id: 'ver-1',
        agent_id: mockAgent.id,
        version_number: 1,
        system_prompt: 'You are Deepti, the front-desk clinic receptionist for Physio One.',
        model_identifier: 'muse-v1',
        temperature: 0.2,
        max_tokens: 1024,
        allowed_tools: ['check_availability'],
        change_summary: 'Initial baseline for Task 7',
        created_at: new Date().toISOString(),
      },
    ]);

    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('Deepti')).toBeInTheDocument();
    });

    // Click "v1" or version history trigger
    fireEvent.click(screen.getByRole('button', { name: /History/i }));

    await waitFor(() => {
      expect(screen.getByText(/Version History — Deepti/i)).toBeInTheDocument();
      expect(screen.getByText('Version 1')).toBeInTheDocument();
      expect(screen.getByText(/Initial baseline for Task 7/i)).toBeInTheDocument();
    });
  });
});
