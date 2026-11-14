'use client';

import React from 'react';
import { Card, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Megaphone } from 'lucide-react';

export default function CampaignsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Patient Retention Campaigns</h1>
        <p className="text-sm text-slate-500">Scheduled broadcast campaigns with eligibility checks and opt-out filters.</p>
      </div>

      <Alert variant="info" title="Campaign Management Module">
        Targeted campaign broadcasts will be scheduled via Celery workers in Task 7.
      </Alert>

      <Card className="border-dashed border-slate-300 bg-slate-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="p-3 bg-amber-100 rounded-full text-amber-700">
            <Megaphone className="h-8 w-8" />
          </div>
          <CardTitle className="text-lg">Campaign Pipeline Prepared</CardTitle>
          <CardDescription className="max-w-md text-xs">
            `campaigns` and `campaign_recipients` database models are migrated and ready for batch execution.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}
