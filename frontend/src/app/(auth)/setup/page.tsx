'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { Eye, EyeOff, ShieldCheck, CheckCircle2 } from 'lucide-react';

export default function SetupPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCheckingSetup, setIsCheckingSetup] = useState(true);
  const [isAlreadyInitialized, setIsAlreadyInitialized] = useState(false);

  useEffect(() => {
    let isMounted = true;
    async function checkSetup() {
      try {
        const status = await api.getSetupStatus();
        if (isMounted) {
          if (status.is_initialized) {
            setIsAlreadyInitialized(true);
          }
        }
      } catch {
        // If error checking setup status, remain on page or show alert
      } finally {
        if (isMounted) setIsCheckingSetup(false);
      }
    }
    checkSetup();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!fullName.trim() || !email.trim() || !password) {
      setErrorMessage('All fields are required.');
      return;
    }

    if (password.length < 8) {
      setErrorMessage('Password must be at least 8 characters long.');
      return;
    }

    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match.');
      return;
    }

    setIsSubmitting(true);
    try {
      await api.setupInitialOwner({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
      });

      // Refresh auth state to load newly authenticated session
      await refreshUser();
      router.push('/dashboard');
    } catch (err: any) {
      setErrorMessage(err.message || 'System setup failed. The system may already be initialized.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isCheckingSetup) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-slate-500">Inspecting initial setup requirements...</p>
      </Card>
    );
  }

  if (isAlreadyInitialized) {
    return (
      <Card className="shadow-lg border-slate-200">
        <CardHeader className="text-center space-y-2">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <CardTitle className="text-xl">Setup Already Completed</CardTitle>
          <CardDescription>
            The initial clinic Owner account has already been provisioned for Physio One.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center space-y-4">
          <p className="text-sm text-slate-600">
            For security reasons, the initial initialization form is locked. Please sign in with your clinic credentials.
          </p>
        </CardContent>
        <CardFooter>
          <Link href="/login" className="w-full">
            <Button className="w-full bg-teal-600 hover:bg-teal-700">
              Return to Sign In
            </Button>
          </Link>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card className="shadow-lg border-slate-200/80">
      <CardHeader className="space-y-1">
        <div className="flex items-center gap-2 text-teal-700 font-semibold text-xs tracking-wider uppercase">
          <ShieldCheck className="h-4 w-4" /> Initial Setup Wizard
        </div>
        <CardTitle className="text-xl">Create Clinic Owner</CardTitle>
        <CardDescription>
          Establish the primary administrator account for Physio One. This account will possess full administrative control.
        </CardDescription>
      </CardHeader>

      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-4">
          {errorMessage && (
            <Alert variant="destructive" title="Setup Error">
              {errorMessage}
            </Alert>
          )}

          <div className="space-y-1">
            <Input
              label="Full Name"
              id="full_name"
              placeholder="Dr. John Doe"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="space-y-1">
            <Input
              label="Clinic Administrator Email"
              id="email"
              type="email"
              placeholder="admin@physioone.com"
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
              Master Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="At least 8 characters"
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

          <div className="space-y-1">
            <Input
              label="Confirm Password"
              id="confirm_password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Re-enter password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>
        </CardContent>

        <CardFooter className="flex flex-col space-y-3">
          <Button
            type="submit"
            className="w-full bg-teal-600 hover:bg-teal-700"
            isLoading={isSubmitting}
            disabled={isSubmitting}
          >
            Initialize Clinic Platform
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
