'use client';

import React from 'react';
import { Card, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { Calendar } from 'lucide-react';

export default function AppointmentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Clinical Appointments</h1>
        <p className="text-sm text-slate-500">Real-time scheduling, practitioner calendar, and Sunday closure policy.</p>
      </div>

      <Alert variant="warning" title="Clinical Invariant: Sunday Closure Enforced">
        Physio One is strictly closed on Sundays. The appointment booking service will automatically reject all Sunday booking requests across both AI and operator channels.
      </Alert>

      <Card className="border-dashed border-slate-300 bg-slate-50/50">
        <CardContent className="flex flex-col items-center justify-center py-16 text-center space-y-3">
          <div className="p-3 bg-indigo-100 rounded-full text-indigo-700">
            <Calendar className="h-8 w-8" />
          </div>
          <CardTitle className="text-lg">Appointments Engine Scaffolding</CardTitle>
          <CardDescription className="max-w-md text-xs">
            `appointments` and `appointment_slots` tables are prepared for ACID reservation locks in Task 6.
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}
