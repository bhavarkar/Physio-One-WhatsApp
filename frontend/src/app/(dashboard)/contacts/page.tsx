'use client';

import React from 'react';
import { Card, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Users } from 'lucide-react';

export default function ContactsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Patients & Contacts</h1>
        <p className="text-sm text-slate-500">Physio One patient repository, communication preferences, and consent registry.</p>
      </div>

      <Alert variant="info" title="Patient Records Module">
        Contact management, interaction histories, and clinical opt-out consent tracking will activate with upcoming clinical pipeline tasks.
      </Alert>

      <Card className="border-dashed border-slate-300 bg-slate-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="p-3 bg-blue-100 rounded-full text-blue-700">
            <Users className="h-8 w-8" />
          </div>
          <CardTitle className="text-lg">Patient Repository Scaffolding</CardTitle>
          <CardDescription className="max-w-md text-xs">
            `contacts` and `patient_consents` tables are indexed and protected against multi-tenant leaks.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}
