'use client';

import React from 'react';
import { useAuth } from '@/lib/auth-context';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import {
  MessageSquare,
  Users,
  Calendar,
  Megaphone,
  Bot,
  Clock,
  Sparkles,
  Info,
  ShieldCheck,
  ArrowRight,
} from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();

  const placeholderCards = [
    {
      title: 'WhatsApp Live Inbox',
      description: 'Unified multi-provider messaging interface for Meta Cloud API and YCloud with automated human takeover handoff.',
      status: 'Awaiting Adapter Setup (Task 5)',
      icon: MessageSquare,
      color: 'text-teal-600 bg-teal-50',
    },
    {
      title: 'Patient Directory & Consents',
      description: 'Single-organization patient repository with strict consent tracking, phone matching, and interaction history.',
      status: 'Schema Ready & Migrated',
      icon: Users,
      color: 'text-blue-600 bg-blue-50',
    },
    {
      title: 'Clinical Appointments Engine',
      description: 'Availability slot calculation, ACID booking locks, and strict Sunday closure enforcement for Physio One.',
      status: 'Awaiting Business Service (Task 6)',
      icon: Calendar,
      color: 'text-indigo-600 bg-indigo-50',
    },
    {
      title: 'Patient Retention Campaigns',
      description: 'Targeted broadcast campaigns, opt-out compliance checks, and scheduled outreach for patient wellness.',
      status: 'Awaiting Worker Scheduler (Task 7)',
      icon: Megaphone,
      color: 'text-amber-600 bg-amber-50',
    },
    {
      title: 'Deepti Clinical AI Agents',
      description: 'Context-grounded triage agents powered by pgvector semantic memory and Physio One protocol knowledge bases.',
      status: 'Awaiting Agent Orchestration (Task 8)',
      icon: Bot,
      color: 'text-purple-600 bg-purple-50',
    },
    {
      title: 'Automated Follow-ups & Reminders',
      description: 'Post-consultation follow-up scheduling, automated WhatsApp check-ins, and feedback capture.',
      status: 'Awaiting Celery Pipeline (Task 9)',
      icon: Clock,
      color: 'text-rose-600 bg-rose-50',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-teal-100 bg-gradient-to-r from-teal-50 via-teal-50/50 to-white p-6 shadow-sm">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">
              Welcome back, {user?.full_name}
            </h1>
            <Badge variant="owner" className="capitalize">
              {user?.role?.name || 'Staff'}
            </Badge>
          </div>
          <p className="text-sm text-slate-600">
            Physio One Clinical WhatsApp AI Agent Management Console &bull; Single Organization Edition
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-teal-800 bg-teal-100/70 px-3 py-2 rounded-lg border border-teal-200">
          <ShieldCheck className="h-4 w-4 text-teal-700" />
          <span>RBAC Verified: {user?.role?.name} Permissions Active</span>
        </div>
      </div>

      {/* Configuration Status Notice */}
      <Alert variant="info" title="System Scaffolding & Configuration Notice">
        Physio One is currently operating in structured foundation mode. The core database schema, Alembic migrations, authentication, RBAC, and frontend application shell are fully landed. Operational features below will activate progressively as their respective backend engine tasks complete.
      </Alert>

      {/* Grid of Subsystem Modules */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-900">
            Clinical AI Platform Modules
          </h2>
          <span className="text-xs text-slate-500 font-medium">
            Phased Rollout Architecture
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {placeholderCards.map((card) => {
            const Icon = card.icon;
            return (
              <Card key={card.title} className="hover:shadow-md transition-shadow border-slate-200">
                <CardHeader className="flex flex-row items-start justify-between pb-2 space-y-0">
                  <div className={`p-2.5 rounded-lg ${card.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <Badge variant="outline" className="text-[11px] bg-slate-50">
                    {card.status}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-2 pt-2">
                  <CardTitle className="text-base font-semibold">{card.title}</CardTitle>
                  <CardDescription className="text-xs leading-relaxed text-slate-500">
                    {card.description}
                  </CardDescription>
                </CardContent>
                <CardFooter className="pt-0 text-xs font-medium text-slate-400">
                  <span>Single-organization pipeline</span>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
