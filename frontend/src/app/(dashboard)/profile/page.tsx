'use client';

import React, { useState, useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import { api, UserSession } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/table';
import {
  User as UserIcon,
  KeyRound,
  Shield,
  Smartphone,
  Laptop,
  Trash2,
  CheckCircle2,
  Lock,
} from 'lucide-react';

export default function ProfilePage() {
  const { user } = useAuth();

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [revokeOtherSessions, setRevokeOtherSessions] = useState(true);
  const [passwordStatus, setPasswordStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  // Active sessions state
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [sessionActionStatus, setSessionActionStatus] = useState<string | null>(null);

  const fetchSessions = async () => {
    try {
      setIsLoadingSessions(true);
      const data = await api.getSessions();
      setSessions(data);
    } catch {
      // Non-critical session list error
    } finally {
      setIsLoadingSessions(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordStatus(null);

    if (!currentPassword || !newPassword) {
      setPasswordStatus({ type: 'error', message: 'Current and new passwords are required.' });
      return;
    }

    if (newPassword.length < 8) {
      setPasswordStatus({ type: 'error', message: 'New password must be at least 8 characters long.' });
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordStatus({ type: 'error', message: 'New passwords do not match.' });
      return;
    }

    setIsChangingPassword(true);
    try {
      const res = await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        revoke_other_sessions: revokeOtherSessions,
      });
      setPasswordStatus({ type: 'success', message: res.message || 'Password successfully updated.' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      await fetchSessions();
    } catch (err: any) {
      setPasswordStatus({ type: 'error', message: err.message || 'Failed to update password. Verify current password.' });
    } finally {
      setIsChangingPassword(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    try {
      await api.revokeSession(sessionId);
      setSessionActionStatus('Session revoked successfully.');
      await fetchSessions();
      setTimeout(() => setSessionActionStatus(null), 4000);
    } catch (err: any) {
      setSessionActionStatus(err.message || 'Failed to revoke session.');
    }
  };

  const handleRevokeAllOther = async () => {
    try {
      const res = await api.revokeAllOtherSessions();
      setSessionActionStatus(res.message);
      await fetchSessions();
      setTimeout(() => setSessionActionStatus(null), 4000);
    } catch (err: any) {
      setSessionActionStatus(err.message || 'Failed to revoke other sessions.');
    }
  };

  if (!user) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Staff Profile & Security
        </h1>
        <p className="text-sm text-slate-500">
          Manage your account credentials, security preferences, and active sessions.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* User Information Card */}
        <div className="space-y-6 lg:col-span-1">
          <Card className="border-slate-200">
            <CardHeader className="space-y-1">
              <div className="flex items-center gap-2 text-teal-700 font-semibold text-xs tracking-wider uppercase">
                <UserIcon className="h-4 w-4" /> Account Information
              </div>
              <CardTitle className="text-lg">Staff Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <span className="block text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Full Name
                </span>
                <span className="font-semibold text-slate-900 text-base">
                  {user.full_name}
                </span>
              </div>
              <div>
                <span className="block text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Email Address
                </span>
                <span className="font-medium text-slate-700">
                  {user.email}
                </span>
              </div>
              <div>
                <span className="block text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Assigned Role
                </span>
                <div className="mt-1">
                  <Badge variant="owner">{user.role?.name || 'Staff'}</Badge>
                </div>
              </div>
              <div>
                <span className="block text-xs font-medium text-slate-500 uppercase tracking-wider">
                  Account Status
                </span>
                <div className="mt-1">
                  <Badge variant={user.is_active ? 'success' : 'destructive'}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              </div>
              <div className="pt-2 border-t border-slate-100 text-xs text-slate-400">
                Created on {new Date(user.created_at).toLocaleDateString()}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Password Change Card */}
        <div className="space-y-6 lg:col-span-2">
          <Card className="border-slate-200">
            <CardHeader className="space-y-1">
              <div className="flex items-center gap-2 text-teal-700 font-semibold text-xs tracking-wider uppercase">
                <KeyRound className="h-4 w-4" /> Credentials
              </div>
              <CardTitle className="text-lg">Change Password</CardTitle>
              <CardDescription>
                Ensure your account uses a strong password of at least 8 characters.
              </CardDescription>
            </CardHeader>

            <form onSubmit={handlePasswordChange}>
              <CardContent className="space-y-4">
                {passwordStatus && (
                  <Alert
                    variant={passwordStatus.type === 'success' ? 'success' : 'destructive'}
                    title={passwordStatus.type === 'success' ? 'Success' : 'Error'}
                  >
                    {passwordStatus.message}
                  </Alert>
                )}

                <div className="space-y-1">
                  <Input
                    label="Current Password"
                    id="current_password"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                    disabled={isChangingPassword}
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Input
                      label="New Password"
                      id="new_password"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      disabled={isChangingPassword}
                    />
                  </div>
                  <div className="space-y-1">
                    <Input
                      label="Confirm New Password"
                      id="confirm_new_password"
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      disabled={isChangingPassword}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    id="revoke_other_sessions"
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                    checked={revokeOtherSessions}
                    onChange={(e) => setRevokeOtherSessions(e.target.checked)}
                    disabled={isChangingPassword}
                  />
                  <label htmlFor="revoke_other_sessions" className="text-sm text-slate-700 cursor-pointer">
                    Sign out of all other active browser sessions on other devices
                  </label>
                </div>
              </CardContent>

              <CardFooter className="flex justify-end">
                <Button
                  type="submit"
                  className="bg-teal-600 hover:bg-teal-700"
                  isLoading={isChangingPassword}
                  disabled={isChangingPassword}
                >
                  Update Password
                </Button>
              </CardFooter>
            </form>
          </Card>

          {/* Active Sessions Card */}
          <Card className="border-slate-200">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
              <div>
                <CardTitle className="text-lg">Active Sessions</CardTitle>
                <CardDescription>
                  Review active sign-in sessions for this user account.
                </CardDescription>
              </div>
              {sessions.filter((s) => !s.is_current).length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRevokeAllOther}
                  className="text-xs text-rose-600 hover:bg-rose-50 border-rose-200"
                >
                  Revoke All Others
                </Button>
              )}
            </CardHeader>

            <CardContent>
              {sessionActionStatus && (
                <div className="mb-4">
                  <Alert variant="info">{sessionActionStatus}</Alert>
                </div>
              )}

              {isLoadingSessions ? (
                <p className="text-sm text-slate-500 py-4 text-center">Loading active sessions...</p>
              ) : sessions.length === 0 ? (
                <p className="text-sm text-slate-500 py-4 text-center">No active sessions found.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Device / Client</TableHead>
                      <TableHead>IP Address</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sessions.map((sess) => (
                      <TableRow key={sess.id}>
                        <TableCell className="font-medium text-xs">
                          <div className="flex items-center gap-2">
                            <Laptop className="h-4 w-4 text-slate-400 shrink-0" />
                            <span className="truncate max-w-[200px]" title={sess.user_agent || 'Unknown'}>
                              {sess.user_agent ? sess.user_agent.split(' ')[0] : 'Web Client'}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="text-xs font-mono text-slate-500">
                          {sess.ip_address || '127.0.0.1'}
                        </TableCell>
                        <TableCell className="text-xs text-slate-500">
                          {new Date(sess.created_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell>
                          {sess.is_current ? (
                            <Badge variant="success">Current Session</Badge>
                          ) : (
                            <Badge variant="outline">Active</Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          {!sess.is_current && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 h-7"
                              onClick={() => handleRevokeSession(sess.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5 mr-1" /> Revoke
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
