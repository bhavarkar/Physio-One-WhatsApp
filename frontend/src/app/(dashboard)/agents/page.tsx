'use client';

import React from 'react';
import { Card, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Bot } from 'lucide-react';

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Deepti Clinical AI Agents</h1>
        <p className="text-sm text-slate-500">Autonomous triage, appointment inquiry handler, and knowledge retrieval agents.</p>
      </div>

      <Alert variant="info" title="AI Agent Framework Module">
        Agent prompt versioning, pgvector knowledge retrieval, and tool calling definitions will activate in Task 8.
      </Alert>

      <Card className="border-dashed border-slate-300 bg-slate-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="p-3 bg-purple-100 rounded-full text-purple-700">
            <Bot className="h-8 w-8" />
          </div>
          <CardTitle className="text-lg">Agent Orchestration Foundation</CardTitle>
          <CardDescription className="max-w-md text-xs">
            `ai_agents`, `agent_versions`, and `knowledge_chunks` (with pgvector HNSW indexing) are established in the database.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}
