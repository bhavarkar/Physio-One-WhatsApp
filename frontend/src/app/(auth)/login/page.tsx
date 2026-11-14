'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import { api } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { Eye, EyeOff, Lock, Mail, ShieldAlert } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const { login, isAuthenticated } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingSetup, setIsCheckingSetup] = useState(true);

  // Check setup status and existing authentication
  useEffect(() => {
    let isMounted = true;
    async function checkSetup() {
      try {
        const status = await api.getSetupStatus();
        if (isMounted && !status.is_initialized) {
          router.replace('/setup');
          return;
        }
      } catch {
        // If status check fails, allow login attempt
      } finally {
        if (isMounted) setIsCheckingSetup(false);
      }
    }

    if (isAuthenticated) {
      router.replace('/dashboard');
    } else {
      checkSetup();
    }

    return () => {
      isMounted = false;
    };
  }, [isAuthenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!email.trim() || !password) {
      setErrorMessage('Please enter both your email address and password.');
      return;
    }

    setIsSubmitting(true);
    try {
      await login(email.trim(), password);
      router.push('/dashboard');
    } catch {
      // Generic error message for security - never reveal whether the account exists
      setErrorMessage('Invalid email or password. Please verify your credentials.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isCheckingSetup) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-slate-500">Checking system configuration...</p>
      </Card>
    );
  }

  return (
    <Card className="shadow-lg border-slate-200/80">
      <CardHeader className="space-y-1">
        <CardTitle className="text-xl">Staff Sign In</CardTitle>
        <CardDescription>
          Enter your staff credentials to access the Physio One portal.
        </CardDescription>
      </CardHeader>

      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          {errorMessage && (
            <Alert variant="destructive" title="Authentication Error">
              {errorMessage}
            </Alert>
          )}

          <div className="space-y-1">
            <Input
              label="Staff Email"
              id="email"
              type="email"
              autoComplete="email"
              placeholder="operator@physioone.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="space-y-1">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-slate-700"
            >
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="••••••••••••"
                className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 pr-10 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500 disabled:opacity-50"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
            <span className="flex items-center gap-1">
              <Lock className="h-3 w-3 text-slate-400" /> Secure HttpOnly Session
            </span>
            <Link
              href="/forgot-password"
              className="text-teal-600 hover:text-teal-700 hover:underline"
            >
              Forgot password?
            </Link>
          </div>
        </CardContent>

        <CardFooter className="flex flex-col space-y-3">
          <Button
            type="submit"
            className="w-full bg-teal-600 hover:bg-teal-700"
            isLoading={isSubmitting}
            disabled={isSubmitting}
          >
            Sign In to Console
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
