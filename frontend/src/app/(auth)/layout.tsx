import React from 'react';
import { Activity } from 'lucide-react';

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-slate-50 to-slate-100 p-4 sm:p-6 lg:p-8">
      <div className="w-full max-w-md space-y-6">
        {/* Physio One Brand Header */}
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-600 text-white shadow-md shadow-teal-600/20">
            <Activity className="h-6 w-6 stroke-[2.5]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Physio One
            </h1>
            <p className="text-xs font-semibold tracking-wider uppercase text-teal-700">
              Clinical WhatsApp AI Platform
            </p>
          </div>
        </div>

        {/* Auth Content */}
        {children}

        {/* Footer */}
        <p className="text-center text-xs text-slate-400">
          Single-Organization Edition &bull; Protected Health Information
        </p>
      </div>
    </div>
  );
}
