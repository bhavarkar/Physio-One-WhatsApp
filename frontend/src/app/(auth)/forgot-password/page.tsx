'use client';

import React from 'react';
import Link from 'next/link';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { ArrowLeft, ShieldAlert } from 'lucide-react';

export default function ForgotPasswordPage() {
  return (
    <Card className="shadow-lg border-slate-200/80">
      <CardHeader className="space-y-1">
        <CardTitle className="text-xl">Password Reset Policy</CardTitle>
        <CardDescription>
          Security controls regarding staff account recovery.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <Alert variant="warning" title="Clinical Data Security Notice">
          In compliance with medical security standards and PHI confidentiality regulations, self-service unauthenticated password reset via email or SMS is disabled for the Physio One single-organization deployment.
        </Alert>

        <div className="rounded-lg bg-slate-50 border border-slate-200 p-4 text-sm text-slate-700 space-y-2">
          <p className="font-semibold text-slate-900">How to recover access:</p>
          <ul className="list-disc pl-5 space-y-1 text-slate-600">
            <li>Contact your clinic <strong>Owner</strong> or <strong>System Administrator</strong> directly.</li>
            <li>An administrator can update your password or re-issue an account from the User Management console.</li>
            <li>If you are the clinic Owner and lost access, consult the server deployment recovery procedures in the operational documentation.</li>
          </ul>
        </div>
      </CardContent>

      <CardFooter>
        <Link href="/login" className="w-full">
          <Button variant="outline" className="w-full flex items-center justify-center gap-2">
            <ArrowLeft className="h-4 w-4" /> Return to Sign In
          </Button>
        </Link>
      </CardFooter>
    </Card>
  );
}
