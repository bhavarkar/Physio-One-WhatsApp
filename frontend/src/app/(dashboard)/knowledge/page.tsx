'use client';

import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  Plus,
  Upload,
  RefreshCw,
  Search,
  FileText,
  Trash2,
  Archive,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Layers,
  Database,
  Sliders,
  ShieldCheck,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import {
  apiClient,
  KnowledgeBase,
  KnowledgeDocument,
  KnowledgeSearchResponse,
} from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Dialog } from '@/components/ui/dialog';

export default function KnowledgePage() {
  const { role } = useAuth();
  const canManage = role === 'Owner' || role === 'Admin';

  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string>('');
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modals
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [showCreateKbModal, setShowCreateKbModal] = useState<boolean>(false);

  // Upload Form
  const [uploadTitle, setUploadTitle] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadChunkSize, setUploadChunkSize] = useState<number>(500);
  const [uploadChunkOverlap, setUploadChunkOverlap] = useState<number>(100);
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Create KB Form
  const [newKbName, setNewKbName] = useState<string>('');
  const [newKbDescription, setNewKbDescription] = useState<string>('');
  const [creatingKb, setCreatingKb] = useState<boolean>(false);

  // Semantic Retrieval Test Console
  const [testQuery, setTestQuery] = useState<string>('What are the clinic operating hours?');
  const [testTopK, setTestTopK] = useState<number>(3);
  const [testThreshold, setTestThreshold] = useState<number>(0.30);
  const [runningSearch, setRunningSearch] = useState<boolean>(false);
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Load Knowledge Bases
  const loadKnowledgeBases = async () => {
    try {
      const kbs = await apiClient.getKnowledgeBases(false);
      setKnowledgeBases(kbs);
      if (kbs.length > 0 && !selectedKbId) {
        setSelectedKbId(kbs[0].id);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load knowledge bases.');
    }
  };

  // Load Documents for selected KB
  const loadDocuments = async (kbId: string) => {
    if (!kbId) return;
    try {
      const docs = await apiClient.getKnowledgeDocuments(kbId);
      setDocuments(docs);
    } catch (err: any) {
      setError(err.message || 'Failed to load documents.');
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadKnowledgeBases();
      setLoading(false);
    };
    init();
  }, []);

  useEffect(() => {
    if (selectedKbId) {
      loadDocuments(selectedKbId);
    }
  }, [selectedKbId]);

  // Handle Document Upload
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setUploadError('Please select a document file (.pdf, .docx, .txt, .md).');
      return;
    }
    if (!uploadTitle.trim()) {
      setUploadError('Please provide a document title.');
      return;
    }
    if (!selectedKbId) {
      setUploadError('Please select a destination Knowledge Base.');
      return;
    }

    setUploading(true);
    setUploadError(null);

    try {
      const formData = new FormData();
      formData.append('knowledge_base_id', selectedKbId);
      formData.append('title', uploadTitle.trim());
      formData.append('file', selectedFile);
      formData.append('chunk_size', uploadChunkSize.toString());
      formData.append('chunk_overlap', uploadChunkOverlap.toString());

      await apiClient.uploadKnowledgeDocument(formData);
      setSuccessMsg(`Document "${uploadTitle}" uploaded and indexed successfully.`);
      setShowUploadModal(false);
      setUploadTitle('');
      setSelectedFile(null);
      await loadDocuments(selectedKbId);
      await loadKnowledgeBases();
    } catch (err: any) {
      setUploadError(err.message || 'Document ingestion failed.');
    } finally {
      setUploading(false);
    }
  };

  // Handle Create Knowledge Base
  const handleCreateKbSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKbName.trim()) return;

    setCreatingKb(true);
    try {
      const created = await apiClient.createKnowledgeBase({
        name: newKbName.trim(),
        description: newKbDescription.trim() || undefined,
        embedding_model: 'text-embedding-3-small',
        vector_dimension: 1536,
      });
      setSuccessMsg(`Knowledge Base "${created.name}" created successfully.`);
      setShowCreateKbModal(false);
      setNewKbName('');
      setNewKbDescription('');
      await loadKnowledgeBases();
      setSelectedKbId(created.id);
    } catch (err: any) {
      setError(err.message || 'Failed to create Knowledge Base.');
    } finally {
      setCreatingKb(false);
    }
  };

  // Handle Document Reprocess
  const handleReprocess = async (docId: string, title: string) => {
    try {
      await apiClient.reprocessDocument(docId);
      setSuccessMsg(`Document "${title}" scheduled for reprocessing.`);
      await loadDocuments(selectedKbId);
    } catch (err: any) {
      setError(err.message || 'Failed to reprocess document.');
    }
  };

  // Handle Document Archive
  const handleArchive = async (docId: string, title: string) => {
    try {
      await apiClient.archiveDocument(docId);
      setSuccessMsg(`Document "${title}" archived. Chunks excluded from active search.`);
      await loadDocuments(selectedKbId);
    } catch (err: any) {
      setError(err.message || 'Failed to archive document.');
    }
  };

  // Handle Document Delete
  const handleDeleteDoc = async (docId: string, title: string) => {
    if (!confirm(`Are you sure you want to permanently delete "${title}" and all its vector chunks?`)) {
      return;
    }
    try {
      await apiClient.deleteKnowledgeDocument(docId);
      setSuccessMsg(`Document "${title}" deleted.`);
      await loadDocuments(selectedKbId);
      await loadKnowledgeBases();
    } catch (err: any) {
      setError(err.message || 'Failed to delete document.');
    }
  };

  // Handle Semantic Retrieval Test
  const handleTestSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testQuery.trim()) return;

    setRunningSearch(true);
    setSearchError(null);
    setSearchResults(null);

    try {
      const res = await apiClient.testKnowledgeRetrieval({
        query: testQuery.trim(),
        knowledge_base_id: selectedKbId || undefined,
        top_k: testTopK,
        similarity_threshold: testThreshold,
      });
      setSearchResults(res);
    } catch (err: any) {
      setSearchError(err.message || 'Retrieval search failed.');
    } finally {
      setRunningSearch(false);
    }
  };

  const selectedKb = knowledgeBases.find((k) => k.id === selectedKbId);
  const totalChunks = documents.reduce((sum, d) => sum + (d.chunk_count || 0), 0);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <BookOpen className="w-7 h-7 text-emerald-600" />
            Clinic Knowledge Base & RAG
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Authoritative clinic documentation, approved treatment protocols, FAQs, and semantic vector storage.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadKnowledgeBases();
              if (selectedKbId) loadDocuments(selectedKbId);
            }}
            disabled={loading}
          >
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>

          {canManage && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCreateKbModal(true)}
              >
                <Plus className="w-4 h-4 mr-1" />
                New Collection
              </Button>
              <Button
                size="sm"
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={() => setShowUploadModal(true)}
                disabled={!selectedKbId}
              >
                <Upload className="w-4 h-4 mr-1" />
                Upload Document
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="w-4 h-4 mr-2" />
          <span>{error}</span>
        </Alert>
      )}
      {successMsg && (
        <Alert variant="success">
          <CheckCircle2 className="w-4 h-4 mr-2" />
          <span>{successMsg}</span>
        </Alert>
      )}

      {/* Knowledge Base Overview Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Collections</p>
                <h3 className="text-2xl font-bold text-slate-900 mt-1">{knowledgeBases.length}</h3>
              </div>
              <div className="p-3 bg-blue-50 text-blue-600 rounded-lg">
                <Database className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">Active Knowledge Bases</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Indexed Documents</p>
                <h3 className="text-2xl font-bold text-slate-900 mt-1">
                  {documents.filter((d) => d.status === 'ready').length}
                </h3>
              </div>
              <div className="p-3 bg-emerald-50 text-emerald-600 rounded-lg">
                <FileText className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">{documents.length} total files uploaded</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Vector Chunks</p>
                <h3 className="text-2xl font-bold text-slate-900 mt-1">{totalChunks}</h3>
              </div>
              <div className="p-3 bg-purple-50 text-purple-600 rounded-lg">
                <Layers className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">pgvector HNSW cosine indexed</p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Embedding Model</p>
                <h3 className="text-sm font-semibold text-slate-900 mt-1 truncate" title={selectedKb?.embedding_model || 'text-embedding-3-small'}>
                  {selectedKb?.embedding_model || 'text-embedding-3-small'}
                </h3>
              </div>
              <div className="p-3 bg-amber-50 text-amber-600 rounded-lg">
                <ShieldCheck className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs text-slate-400 mt-2">{selectedKb?.vector_dimension || 1536}-dim unit vectors</p>
          </CardContent>
        </Card>
      </div>

      {/* Collection Selector Bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-slate-50 p-3 rounded-lg border">
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <span className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Active Collection:</span>
          <select
            className="text-sm font-medium bg-white border border-slate-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={selectedKbId}
            onChange={(e) => setSelectedKbId(e.target.value)}
          >
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name} ({kb.document_count} docs)
              </option>
            ))}
          </select>
        </div>
        {selectedKb && (
          <p className="text-xs text-slate-500 italic">
            {selectedKb.description || 'No description provided.'}
          </p>
        )}
      </div>

      {/* Main Grid: Left = Documents Table, Right = Semantic Search Test Console */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Documents Table (2 Cols) */}
        <div className="lg:col-span-2 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <FileText className="w-4 h-4 text-slate-600" />
                    Knowledge Documents
                  </CardTitle>
                  <CardDescription className="text-xs text-slate-500">
                    Approved documents in this collection. Only &quot;Ready&quot; documents are accessible to AI agents.
                  </CardDescription>
                </div>
                <Badge variant="outline" className="text-xs">
                  {documents.length} files
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {documents.length === 0 ? (
                <div className="py-12 text-center text-slate-500">
                  <BookOpen className="w-10 h-10 mx-auto text-slate-300 mb-2" />
                  <p className="text-sm font-medium">No documents uploaded yet.</p>
                  <p className="text-xs text-slate-400 mt-1">
                    Upload clinic guidelines, operating hours, pricing, or FAQ files (.pdf, .docx, .txt, .md).
                  </p>
                  {canManage && (
                    <Button
                      size="sm"
                      className="mt-4 bg-emerald-600 hover:bg-emerald-700 text-white"
                      onClick={() => setShowUploadModal(true)}
                    >
                      <Upload className="w-4 h-4 mr-1" />
                      Upload First Document
                    </Button>
                  )}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-xs font-semibold text-slate-500 uppercase tracking-wider">
                        <th className="pb-2">Document</th>
                        <th className="pb-2">Type</th>
                        <th className="pb-2">Chunks</th>
                        <th className="pb-2">Status</th>
                        <th className="pb-2">Date</th>
                        {canManage && <th className="pb-2 text-right">Actions</th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {documents.map((doc) => {
                        let statusBadge = (
                          <Badge variant="secondary" className="bg-slate-100 text-slate-700 capitalize text-xs">
                            {doc.status}
                          </Badge>
                        );
                        if (doc.status === 'ready') {
                          statusBadge = (
                            <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100 border-none capitalize text-xs">
                              Ready
                            </Badge>
                          );
                        } else if (doc.status === 'processing' || doc.status === 'pending') {
                          statusBadge = (
                            <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100 border-none capitalize text-xs">
                              Processing
                            </Badge>
                          );
                        } else if (doc.status === 'failed') {
                          statusBadge = (
                            <Badge className="bg-red-100 text-red-800 hover:bg-red-100 border-none capitalize text-xs">
                              Failed
                            </Badge>
                          );
                        } else if (doc.status === 'archived') {
                          statusBadge = (
                            <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100 border-none capitalize text-xs">
                              Archived
                            </Badge>
                          );
                        }

                        return (
                          <tr key={doc.id} className="hover:bg-slate-50/70 transition-colors">
                            <td className="py-3">
                              <div className="font-medium text-slate-900">{doc.title}</div>
                              <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-[200px]">
                                {doc.filename} &bull; {(doc.file_size_bytes / 1024).toFixed(1)} KB (v{doc.version})
                              </div>
                              {doc.error_message && (
                                <div className="text-xs text-red-600 mt-1 flex items-center gap-1">
                                  <AlertCircle className="w-3 h-3" />
                                  {doc.error_message}
                                </div>
                              )}
                            </td>
                            <td className="py-3">
                              <span className="uppercase text-xs font-mono px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded">
                                {doc.file_type}
                              </span>
                            </td>
                            <td className="py-3 font-semibold text-slate-700 text-xs">
                              {doc.chunk_count}
                            </td>
                            <td className="py-3">{statusBadge}</td>
                            <td className="py-3 text-xs text-slate-500 whitespace-nowrap">
                              {new Date(doc.created_at).toLocaleDateString()}
                            </td>
                            {canManage && (
                              <td className="py-3 text-right whitespace-nowrap">
                                <div className="flex items-center justify-end gap-1">
                                  {doc.status === 'failed' && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="h-8 w-8 p-0 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                                      onClick={() => handleReprocess(doc.id, doc.title)}
                                      title="Reprocess Document"
                                    >
                                      <RefreshCw className="w-3.5 h-3.5" />
                                    </Button>
                                  )}
                                  {doc.status === 'ready' && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="h-8 w-8 p-0 text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                                      onClick={() => handleArchive(doc.id, doc.title)}
                                      title="Archive (exclude from search)"
                                    >
                                      <Archive className="w-3.5 h-3.5" />
                                    </Button>
                                  )}
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
                                    onClick={() => handleDeleteDoc(doc.id, doc.title)}
                                    title="Delete Document"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </Button>
                                </div>
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Semantic Retrieval Test Console (1 Col) */}
        <div className="space-y-4">
          <Card className="border-emerald-200/80 bg-gradient-to-b from-white to-emerald-50/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2 text-slate-900">
                <Sparkles className="w-4 h-4 text-emerald-600" />
                RAG Retrieval Console
              </CardTitle>
              <CardDescription className="text-xs text-slate-500">
                Test vector similarity search in real-time across active knowledge chunks.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleTestSearch} className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
                    Semantic Query
                  </label>
                  <Input
                    className="text-sm bg-white"
                    placeholder="e.g. Do you open on Sundays?"
                    value={testQuery}
                    onChange={(e) => setTestQuery(e.target.value)}
                    required
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
                      Top-K Chunks
                    </label>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      className="text-sm bg-white"
                      value={testTopK}
                      onChange={(e) => setTestTopK(parseInt(e.target.value) || 3)}
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
                      Min Similarity
                    </label>
                    <Input
                      type="number"
                      step={0.05}
                      min={0.0}
                      max={1.0}
                      className="text-sm bg-white"
                      value={testThreshold}
                      onChange={(e) => setTestThreshold(parseFloat(e.target.value) || 0.30)}
                    />
                  </div>
                </div>

                <Button
                  type="submit"
                  size="sm"
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white"
                  disabled={runningSearch || !testQuery.trim()}
                >
                  <Search className={`w-4 h-4 mr-2 ${runningSearch ? 'animate-spin' : ''}`} />
                  {runningSearch ? 'Searching Vector Space...' : 'Test Semantic Retrieval'}
                </Button>
              </form>

              {searchError && (
                <div className="mt-4 p-2 text-xs bg-red-50 text-red-700 border border-red-200 rounded">
                  {searchError}
                </div>
              )}

              {/* Retrieval Results */}
              {searchResults && (
                <div className="mt-5 space-y-3 pt-4 border-t">
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">
                      Matches Found: {searchResults.count}
                    </span>
                    <span className="flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3 text-slate-400" />
                      {searchResults.retrieval_latency_ms} ms
                    </span>
                  </div>

                  {searchResults.results.length === 0 ? (
                    <div className="p-3 text-center text-xs text-slate-500 bg-slate-50 rounded border">
                      No matching chunks met the similarity threshold ({testThreshold}).
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                      {searchResults.results.map((r, i) => (
                        <div
                          key={r.chunk_id || i}
                          className="p-3 bg-white border border-slate-200 rounded-lg shadow-sm text-xs space-y-1.5"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-slate-900 truncate max-w-[170px]" title={r.document_title}>
                              {r.document_title} (v{r.document_version})
                            </span>
                            <Badge className="bg-emerald-100 text-emerald-800 text-[10px] font-mono px-1.5 py-0 border-none">
                              {(r.similarity_score * 100).toFixed(1)}% match
                            </Badge>
                          </div>
                          <p className="text-slate-600 text-xs leading-relaxed line-clamp-4 bg-slate-50 p-2 rounded border border-slate-100 font-sans">
                            {r.chunk_text}
                          </p>
                          <div className="text-[10px] text-slate-400 font-mono">
                            Chunk #{r.chunk_index} &bull; {r.knowledge_base_name}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Prompt Injection Defense Notice */}
                  <div className="p-2 bg-emerald-50/60 border border-emerald-100 rounded text-[11px] text-emerald-800 flex items-start gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                    <span>
                      Retrieved chunks are automatically wrapped in boundary guards to protect the AI Agent against prompt injection.
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Upload Document Modal */}
      <Dialog
        isOpen={showUploadModal}
        onClose={() => {
          setShowUploadModal(false);
          setUploadError(null);
        }}
        title="Upload Knowledge Document"
        description="Ingest clinic FAQs, treatment guides, or policy manuals into the vector store."
      >
        <form onSubmit={handleUploadSubmit} className="space-y-4">
          {uploadError && (
            <div className="p-2 text-xs bg-red-50 text-red-700 border border-red-200 rounded">
              {uploadError}
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
              Document Title *
            </label>
            <Input
              placeholder="e.g. Operating Hours & Sunday Policy"
              value={uploadTitle}
              onChange={(e) => setUploadTitle(e.target.value)}
              required
            />
          </div>

          <div>
            <label htmlFor="file-upload" className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
              Select Document File (.pdf, .docx, .txt, .md) *
            </label>
            <input
              id="file-upload"
              type="file"
              accept=".pdf,.docx,.txt,.md,.markdown"
              className="text-xs block w-full text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 cursor-pointer"
              onChange={(e) => {
                const file = e.target.files?.[0] || null;
                setSelectedFile(file);
                if (file && !uploadTitle) {
                  // Pre-populate title from filename without extension
                  const base = file.name.substring(0, file.name.lastIndexOf('.')) || file.name;
                  setUploadTitle(base.replace(/[-_]/g, ' '));
                }
              }}
              required
            />
            <p className="text-[11px] text-slate-400 mt-1">Maximum file size: 10MB.</p>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
                Chunk Size (chars)
              </label>
              <Input
                type="number"
                min={100}
                max={2000}
                value={uploadChunkSize}
                onChange={(e) => setUploadChunkSize(parseInt(e.target.value) || 500)}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
                Chunk Overlap (chars)
              </label>
              <Input
                type="number"
                min={0}
                max={500}
                value={uploadChunkOverlap}
                onChange={(e) => setUploadChunkOverlap(parseInt(e.target.value) || 100)}
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowUploadModal(false)}
              disabled={uploading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
              disabled={uploading || !selectedFile}
            >
              <Upload className={`w-4 h-4 mr-1 ${uploading ? 'animate-spin' : ''}`} />
              {uploading ? 'Ingesting & Chunking...' : 'Upload & Index'}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* Create Knowledge Base Modal */}
      <Dialog
        isOpen={showCreateKbModal}
        onClose={() => setShowCreateKbModal(false)}
        title="Create Knowledge Base Collection"
        description="Organize documents into dedicated collections for clinic departments or topics."
      >
        <form onSubmit={handleCreateKbSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
              Collection Name *
            </label>
            <Input
              placeholder="e.g. Physio One Clinical Protocols"
              value={newKbName}
              onChange={(e) => setNewKbName(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 uppercase tracking-wider block mb-1">
              Description
            </label>
            <Input
              placeholder="e.g. Physiotherapy assessment procedures, treatment packages, and contraindications"
              value={newKbDescription}
              onChange={(e) => setNewKbDescription(e.target.value)}
            />
          </div>

          <div className="p-3 bg-slate-50 rounded border text-xs text-slate-500 space-y-1">
            <div className="flex justify-between">
              <span>Embedding Model:</span>
              <span className="font-mono text-slate-700 font-semibold">text-embedding-3-small</span>
            </div>
            <div className="flex justify-between">
              <span>Vector Dimensions:</span>
              <span className="font-mono text-slate-700 font-semibold">1536</span>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setShowCreateKbModal(false)}
              disabled={creatingKb}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
              disabled={creatingKb || !newKbName.trim()}
            >
              <Plus className={`w-4 h-4 mr-1 ${creatingKb ? 'animate-spin' : ''}`} />
              {creatingKb ? 'Creating...' : 'Create Collection'}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
