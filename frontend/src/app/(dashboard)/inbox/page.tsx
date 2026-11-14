'use client';

import React from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { MessageSquare } from 'lucide-react';

export default function InboxPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Live WhatsApp Inbox</h1>
        <p className="text-sm text-slate-500">Dual-provider messaging stream for Meta Cloud API and YCloud.</p>
      </div>

      <Alert variant="info" title="Task 5 Target Module">
        The WhatsApp Live Inbox, conversational message history, and operator human-takeover toggles will be implemented in Task 5.
      </Alert>

      <Card className="border-dashed border-slate-300 bg-slate-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="p-3 bg-teal-100 rounded-full text-teal-700">
            <MessageSquare className="h-8 w-8" />
          </div>
          <CardTitle className="text-lg">Conversations Workspace Scaffolding Ready</CardTitle>
          <CardDescription className="max-w-md text-xs">
            The database schema (`conversations`, `whatsapp_messages`, `webhook_events`) is migrated. Live webhook ingress and UI messaging will connect next.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}
