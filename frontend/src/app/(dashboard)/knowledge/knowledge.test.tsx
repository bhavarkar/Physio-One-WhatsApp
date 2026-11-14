import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import KnowledgePage from './page';
import { apiClient } from '@/lib/api-client';

const mockKb = {
  id: 'kb-default-1',
  name: 'Physio One Clinic Approved Knowledge Base',
  description: 'Verified clinical treatment guidelines and operating policies.',
  embedding_model: 'text-embedding-3-small',
  vector_dimension: 1536,
  is_active: true,
  created_by_id: 'user-owner-1',
  document_count: 1,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockDoc = {
  id: 'doc-faq-1',
  knowledge_base_id: 'kb-default-1',
  title: 'Operating Hours and Sunday Rules',
  filename: 'hours.txt',
  file_type: 'txt',
  file_url: '/storage/knowledge/kb-default-1/hours.txt',
  file_size_bytes: 2048,
  source_hash: 'abc123hash',
  chunk_count: 3,
  version: 1,
  status: 'ready' as const,
  error_message: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

let mockAuthRole = 'Owner';
jest.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    user: { id: 'user-1', email: 'owner@physioone.test', full_name: 'Owner User' },
    role: mockAuthRole,
    isLoading: false,
    isAuthenticated: true,
  }),
}));

describe('KnowledgePage (Clinic Knowledge Base & RAG Retrieval)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthRole = 'Owner';

    jest.spyOn(apiClient, 'getKnowledgeBases').mockResolvedValue([mockKb]);
    jest.spyOn(apiClient, 'getKnowledgeDocuments').mockResolvedValue([mockDoc]);
    jest.spyOn(apiClient, 'uploadKnowledgeDocument').mockResolvedValue(mockDoc);
    jest.spyOn(apiClient, 'archiveDocument').mockResolvedValue({ ...mockDoc, status: 'archived' });
    jest.spyOn(apiClient, 'deleteKnowledgeDocument').mockResolvedValue(undefined as any);
    jest.spyOn(apiClient, 'testKnowledgeRetrieval').mockResolvedValue({
      query: 'Are you open on Sundays?',
      count: 1,
      retrieval_latency_ms: 42,
      results: [
        {
          chunk_id: 'chunk-1',
          document_id: 'doc-faq-1',
          document_title: 'Operating Hours and Sunday Rules',
          document_version: 1,
          knowledge_base_id: 'kb-default-1',
          knowledge_base_name: 'Physio One Clinic Approved Knowledge Base',
          chunk_index: 0,
          chunk_text: 'Physio One is strictly closed on Sundays. No appointments can be booked on Sundays.',
          similarity_score: 0.88,
        },
      ],
    });
  });

  it('renders Knowledge Base overview stats and document table', async () => {
    render(<KnowledgePage />);

    expect(await screen.findByText('Clinic Knowledge Base & RAG')).toBeInTheDocument();
    expect(await screen.findByText('Operating Hours and Sunday Rules')).toBeInTheDocument();
    expect(screen.getByText('hours.txt • 2.0 KB (v1)')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('allows Owner to open upload modal and upload a document', async () => {
    render(<KnowledgePage />);

    // Wait for knowledge bases and documents to finish loading
    expect(await screen.findByText('Operating Hours and Sunday Rules')).toBeInTheDocument();

    const uploadBtn = screen.getByRole('button', { name: /Upload Document/i });
    fireEvent.click(uploadBtn);

    expect(screen.getByText('Upload Knowledge Document')).toBeInTheDocument();

    const titleInput = screen.getByPlaceholderText('e.g. Operating Hours & Sunday Policy');
    fireEvent.change(titleInput, { target: { value: 'Physiotherapy Pricing' } });

    // Mock file selection
    const file = new File(['Assessment Rs 800'], 'pricing.txt', { type: 'text/plain' });
    const fileInput = screen.getByLabelText(/Select Document File/i);
    fireEvent.change(fileInput, { target: { files: [file] } });

    const submitBtn = screen.getByRole('button', { name: /Upload & Index/i });
    fireEvent.submit(submitBtn.closest('form')!);

    await waitFor(() => {
      expect(apiClient.uploadKnowledgeDocument).toHaveBeenCalledTimes(1);
    });
  });

  it('allows archive of ready document', async () => {
    render(<KnowledgePage />);

    expect(await screen.findByText('Operating Hours and Sunday Rules')).toBeInTheDocument();

    const archiveBtn = screen.getByTitle('Archive (exclude from search)');
    fireEvent.click(archiveBtn);

    await waitFor(() => {
      expect(apiClient.archiveDocument).toHaveBeenCalledWith('doc-faq-1');
    });
  });

  it('executes real-time semantic retrieval test and displays matched chunk', async () => {
    render(<KnowledgePage />);

    expect(await screen.findByText('RAG Retrieval Console')).toBeInTheDocument();

    const searchBtn = screen.getByRole('button', { name: /Test Semantic Retrieval/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(apiClient.testKnowledgeRetrieval).toHaveBeenCalledWith(
        expect.objectContaining({
          query: 'What are the clinic operating hours?',
          knowledge_base_id: 'kb-default-1',
        })
      );
    });

    expect(await screen.findByText('Matches Found: 1')).toBeInTheDocument();
    expect(screen.getByText('88.0% match')).toBeInTheDocument();
    expect(screen.getByText(/strictly closed on Sundays/i)).toBeInTheDocument();
  });

  it('hides upload and creation controls for Operator role (read-only knowledge management)', async () => {
    mockAuthRole = 'Operator';
    render(<KnowledgePage />);

    expect(await screen.findByText('Clinic Knowledge Base & RAG')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Upload Document/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /New Collection/i })).not.toBeInTheDocument();
    // Operator can still use the retrieval test console
    expect(screen.getByRole('button', { name: /Test Semantic Retrieval/i })).toBeInTheDocument();
  });
});
