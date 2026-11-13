'use client';

import React from 'react';
import { Card, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Settings } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Clinic System Settings</h1>
        <p className="text-sm text-slate-500">Single-organization operational configuration, WhatsApp API credentials, and clinic business hours.</p>
      </div>

      <Alert variant="warning" title="Restricted Area: Owner Only">
        This configuration console is strictly accessible only to the clinic Owner account.
      </Alert>

      <Card className="border-dashed border-slate-300 bg-slate-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="p-3 bg-slate-100 rounded-full text-slate-700">
            <Settings className="h-8 w-8" />
          </div>
          <CardTitle className="text-lg">System Settings Foundation</CardTitle>
          <CardDescription className="max-w-md text-xs">
            `system_settings` key-value store with Fernet encryption for secrets is active in the database.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}
