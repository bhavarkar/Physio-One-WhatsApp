import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AgentsPage from './page';
import { apiClient, AIAgent, AIModel, RegisteredTool } from '@/lib/api-client';

const mockAgent: AIAgent = {
  id: 'agent-deepti-1',
  name: 'Deepti',
  description: 'AI Receptionist for Physio One Clinic.',
  is_active: true,
  current_version: 1,
  primary_model_id: 'model-muse-1',
  primary_model_identifier: 'muse-v1',
  primary_provider_name: 'muse',
  fallback_model_id: null,
  fallback_model_identifier: null,
  fallback_provider_name: null,
  temperature: 0.2,
  max_tokens: 1024,
  context_budget_tokens: 4000,
  max_execution_steps: 5,
  execution_timeout_seconds: 30,
  system_prompt: 'You are Deepti, the front-desk clinic receptionist for Physio One.',
  allowed_tools: ['check_availability', 'find_patient'],
  supported_languages: ['en', 'hi'],
  rag_enabled: true,
  rag_top_k: 3,
  rag_similarity_threshold: 0.70,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockModel: AIModel = {
  id: 'model-muse-1',
  provider_id: 'prov-muse-1',
  provider_name: 'muse',
  model_identifier: 'muse-v1',
  display_name: 'Muse v1 Clinical',
  max_context_tokens: 8192,
  supports_tools: false,
  supports_vision: false,
  created_at: new Date().toISOString(),
};

const mockTool: RegisteredTool = {
  name: 'check_availability',
  description: 'Check available appointment slots for a given practitioner and date.',
  is_mutation: false,
  parameters_schema: { type: 'object', properties: { date: { type: 'string' } } },
  requires_permission: 'appointments:read',
  is_idempotent: true,
  timeout_seconds: 10,
  is_enabled: true,
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
      agent_name: 'Deepti',
      provider: 'muse',
      model: 'muse-v1',
      status: 'completed',
      steps: [],
      tool_calls: [],
      total_input_tokens: 42,
      total_output_tokens: 28,
      total_tokens: 70,
      duration_ms: 350,
      response_text: 'Hello! I am Deepti. Physio One is open Monday through Saturday.',
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

    // Verify response text and metrics appear
    await waitFor(() => {
      expect(screen.getByText(/Physio One is open Monday through Saturday/i)).toBeInTheDocument();
      expect(screen.getByText('350ms')).toBeInTheDocument();
    });
  });

  it('opens agent creation modal with default parameters', async () => {
    render(<AgentsPage />);

    await waitFor(() => {
      expect(screen.getByText('Deepti')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Create Agent/i }));

    await waitFor(() => {
      expect(screen.getByText(/Create New AI Agent/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/e\.g\. Deepti/i)).toBeInTheDocument();
    });
  });
});
