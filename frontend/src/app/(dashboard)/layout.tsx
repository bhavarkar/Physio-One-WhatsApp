'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Activity,
  LayoutDashboard,
  MessageSquare,
  Users,
  Calendar,
  Megaphone,
  Bot,
  BookOpen,
  UserCog,
  Settings,
  LogOut,
  Menu,
  X,
  User as UserIcon,
  Loader2,
  ChevronRight,
  Clock,
} from 'lucide-react';

interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
  requiredRoles?: string[];
  badge?: string;
}

const navItems: NavItem[] = [
  {
    name: 'Dashboard',
    href: '/dashboard',
    icon: LayoutDashboard,
  },
  {
    name: 'Live Inbox',
    href: '/inbox',
    icon: MessageSquare,
    requiredRoles: ['Owner', 'Admin', 'Operator'],
    badge: 'Preview',
  },
  {
    name: 'Patients & Contacts',
    href: '/contacts',
    icon: Users,
    requiredRoles: ['Owner', 'Admin', 'Operator'],
  },
  {
    name: 'Appointments',
    href: '/appointments',
    icon: Calendar,
    requiredRoles: ['Owner', 'Admin', 'Operator'],
  },
  {
    name: 'Automations',
    href: '/automations',
    icon: Clock,
    requiredRoles: ['Owner', 'Admin', 'Operator'],
  },
  {
    name: 'Campaigns',
    href: '/campaigns',
    icon: Megaphone,
    requiredRoles: ['Owner', 'Admin'],
  },
  {
    name: 'AI Clinical Agents',
    href: '/agents',
    icon: Bot,
    requiredRoles: ['Owner', 'Admin'],
  },
  {
    name: 'Knowledge Base',
    href: '/knowledge',
    icon: BookOpen,
    requiredRoles: ['Owner', 'Admin', 'Operator'],
  },
  {
    name: 'Staff & Roles',
    href: '/users',
    icon: UserCog,
    requiredRoles: ['Owner', 'Admin'],
  },
  {
    name: 'Clinic Settings',
    href: '/settings',
    icon: Settings,
    requiredRoles: ['Owner'],
  },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, role, isLoading, isAuthenticated, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Protected route enforcement: if not authenticated, redirect to login
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center space-y-3">
          <Loader2 className="h-8 w-8 animate-spin text-teal-600" />
          <p className="text-sm font-medium text-slate-500">Loading Physio One Console...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return null;
  }

  const roleVariant = (roleName?: string): "owner" | "admin" | "operator" | "viewer" => {
    switch (roleName?.toLowerCase()) {
      case 'owner':
        return 'owner';
      case 'admin':
        return 'admin';
      case 'operator':
        return 'operator';
      default:
        return 'viewer';
    }
  };

  const filteredNavItems = navItems.filter((item) => {
    if (!item.requiredRoles) return true;
    return role ? item.requiredRoles.includes(role) : false;
  });

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Mobile Drawer Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar for Desktop & Mobile Drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-100 px-6">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-teal-600 text-white shadow-sm">
              <Activity className="h-5 w-5 stroke-[2.5]" />
            </div>
            <div>
              <span className="font-bold text-slate-900 text-base leading-tight block">
                Physio One
              </span>
              <span className="text-[10px] font-semibold tracking-wider uppercase text-teal-700 block">
                WhatsApp AI
              </span>
            </div>
          </Link>
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="lg:hidden text-slate-500 hover:text-slate-800"
            aria-label="Close sidebar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation Items */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Clinical Operations
          </div>
          {filteredNavItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`group flex items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-teal-50 text-teal-800 font-semibold'
                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon
                    className={`h-4 w-4 shrink-0 transition-colors ${
                      isActive ? 'text-teal-600' : 'text-slate-400 group-hover:text-slate-600'
                    }`}
                  />
                  <span>{item.name}</span>
                </div>
                {item.badge && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </div>

        {/* User Profile Mini Card in Sidebar */}
        <div className="border-t border-slate-100 p-4">
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-2 overflow-hidden">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                <UserIcon className="h-4 w-4" />
              </div>
              <div className="truncate">
                <p className="text-xs font-semibold text-slate-900 truncate">
                  {user.full_name}
                </p>
                <p className="text-[11px] text-slate-500 truncate">{user.email}</p>
              </div>
            </div>
            <Badge variant={roleVariant(user.role?.name)}>
              {user.role?.name || 'Staff'}
            </Badge>
          </div>
          <div className="flex gap-1.5 pt-1">
            <Link href="/profile" className="w-1/2">
              <Button
                variant="outline"
                size="sm"
                className="w-full text-xs h-7"
              >
                Profile
              </Button>
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="w-1/2 text-xs h-7 text-rose-600 hover:text-rose-700 hover:bg-rose-50"
            >
              <LogOut className="h-3.5 w-3.5 mr-1" /> Logout
            </Button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col lg:pl-64">
        {/* Top Header */}
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 sm:px-6 lg:px-8 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-1.5 text-slate-500 hover:text-slate-800"
              aria-label="Open sidebar"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span className="font-medium text-slate-900">Physio One</span>
              <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
              <span className="capitalize">{pathname.replace('/', '') || 'Dashboard'}</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 text-xs text-slate-500">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>Single Organization Node Active</span>
            </div>
            <Link
              href="/profile"
              className="flex items-center gap-2 rounded-full border border-slate-200 py-1 pl-2 pr-3 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              <span className="font-semibold text-slate-900">{user.full_name}</span>
              <Badge variant={roleVariant(user.role?.name)} className="text-[10px] py-0 px-1.5">
                {user.role?.name}
              </Badge>
            </Link>
          </div>
        </header>

        {/* Page Content Container */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
