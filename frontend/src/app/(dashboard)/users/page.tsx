'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { api, User, Role } from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Dialog } from '@/components/ui/dialog';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/table';
import {
  UserPlus,
  Search,
  Shield,
  UserX,
  UserCheck,
  KeyRound,
  RefreshCw,
  AlertTriangle,
  Lock,
} from 'lucide-react';

export default function UsersPage() {
  const { user: currentUser, role: currentRole } = useAuth();

  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Create User Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [selectedRoleId, setSelectedRoleId] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Action Confirmation Modal
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    type: 'deactivate' | 'activate' | 'revoke_sessions';
    user: User | null;
  }>({
    isOpen: false,
    type: 'deactivate',
    user: null,
  });
  const [isActionLoading, setIsActionLoading] = useState(false);

  const fetchUsers = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await api.getUsers({ search: searchQuery.trim() || undefined });
      setUsers(res.users);
      setTotalUsers(res.total);
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to load staff list.' });
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery]);

  const fetchRoles = async () => {
    try {
      const data = await api.getRoles();
      setRoles(data);
      if (data.length > 0 && !selectedRoleId) {
        // Default to Operator role for safe least-privilege creation
        const defaultRole = data.find((r) => r.name === 'Operator') || data[0];
        setSelectedRoleId(defaultRole.id);
      }
    } catch {
      // Role fetch failure
    }
  };

  useEffect(() => {
    fetchUsers();
    fetchRoles();
  }, [fetchUsers]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);

    if (!newName.trim() || !newEmail.trim() || !newPassword || !selectedRoleId) {
      setCreateError('All fields are required.');
      return;
    }

    if (newPassword.length < 8) {
      setCreateError('Password must be at least 8 characters long.');
      return;
    }

    setIsCreating(true);
    try {
      await api.createUser({
        full_name: newName.trim(),
        email: newEmail.trim(),
        password: newPassword,
        role_id: selectedRoleId,
      });

      setFeedback({ type: 'success', message: `Staff member ${newName} successfully created.` });
      setIsCreateOpen(false);
      setNewName('');
      setNewEmail('');
      setNewPassword('');
      await fetchUsers();
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create user.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleExecuteAction = async () => {
    if (!confirmModal.user) return;
    setIsActionLoading(true);
    try {
      if (confirmModal.type === 'deactivate') {
        await api.deactivateUser(confirmModal.user.id);
        setFeedback({ type: 'success', message: `User ${confirmModal.user.full_name} deactivated.` });
      } else if (confirmModal.type === 'activate') {
        await api.updateUser(confirmModal.user.id, { is_active: true });
        setFeedback({ type: 'success', message: `User ${confirmModal.user.full_name} reactivated.` });
      } else if (confirmModal.type === 'revoke_sessions') {
        const res = await api.revokeUserSessions(confirmModal.user.id);
        setFeedback({ type: 'success', message: res.message });
      }
      setConfirmModal({ isOpen: false, type: 'deactivate', user: null });
      await fetchUsers();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Action failed.' });
      setConfirmModal({ isOpen: false, type: 'deactivate', user: null });
    } finally {
      setIsActionLoading(false);
    }
  };

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

  return (
    <div className="space-y-6">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Staff & User Management
          </h1>
          <p className="text-sm text-slate-500">
            Single-organization staff directory, roles, and session access control.
          </p>
        </div>
        <Button
          onClick={() => setIsCreateOpen(true)}
          className="bg-teal-600 hover:bg-teal-700 text-white shrink-0"
        >
          <UserPlus className="h-4 w-4 mr-2" /> Add Staff Member
        </Button>
      </div>

      {feedback && (
        <Alert
          variant={feedback.type === 'success' ? 'success' : 'destructive'}
          title={feedback.type === 'success' ? 'Operation Completed' : 'Operation Error'}
        >
          {feedback.message}
        </Alert>
      )}

      {/* Filter and Search Bar */}
      <Card className="border-slate-200">
        <CardContent className="p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              fetchUsers();
            }}
            className="flex gap-2"
          >
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search staff by full name or email address..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex h-10 w-full rounded-md border border-slate-300 bg-white pl-9 pr-3 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              />
            </div>
            <Button type="submit" variant="secondary">
              Search
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setSearchQuery('');
                fetchUsers();
              }}
              title="Refresh list"
            >
              <RefreshCw className="h-4 w-4" />
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Staff User Table */}
      <Card className="border-slate-200">
        <CardContent className="p-0">
          {isLoading ? (
            <p className="text-sm text-slate-500 py-12 text-center">Loading staff records...</p>
          ) : users.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <p className="text-sm font-medium text-slate-700">No staff members found.</p>
              <p className="text-xs text-slate-400">Try modifying your search criteria.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Staff Member</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Registered</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => {
                  const isSelf = currentUser?.id === u.id;
                  const isTargetOwner = u.role?.name === 'Owner';
                  const canManage = currentRole === 'Owner' || (currentRole === 'Admin' && !isTargetOwner);

                  return (
                    <TableRow key={u.id}>
                      <TableCell>
                        <div className="font-medium text-slate-900">{u.full_name}</div>
                        <div className="text-xs text-slate-500">{u.email}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={roleVariant(u.role?.name)}>
                          {u.role?.name || 'Staff'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={u.is_active ? 'success' : 'destructive'}>
                          {u.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-slate-500">
                        {new Date(u.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-right space-x-1">
                        {canManage && (
                          <>
                            {u.is_active ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={isSelf}
                                onClick={() =>
                                  setConfirmModal({
                                    isOpen: true,
                                    type: 'deactivate',
                                    user: u,
                                  })
                                }
                                className="text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 h-8"
                                title={isSelf ? 'Cannot deactivate your own account' : 'Deactivate user'}
                              >
                                <UserX className="h-3.5 w-3.5 mr-1" /> Deactivate
                              </Button>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setConfirmModal({
                                    isOpen: true,
                                    type: 'activate',
                                    user: u,
                                  })
                                }
                                className="text-xs text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 h-8"
                              >
                                <UserCheck className="h-3.5 w-3.5 mr-1" /> Reactivate
                              </Button>
                            )}

                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setConfirmModal({
                                  isOpen: true,
                                  type: 'revoke_sessions',
                                  user: u,
                                })
                              }
                              className="text-xs text-slate-600 hover:text-slate-900 hover:bg-slate-100 h-8"
                              title="Revoke active login sessions"
                            >
                              <KeyRound className="h-3.5 w-3.5 mr-1" /> Revoke Sessions
                            </Button>
                          </>
                        )}
                        {!canManage && (
                          <span className="text-xs text-slate-400 italic">Protected</span>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create User Modal Dialog */}
      <Dialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Add New Staff Member"
        description="Provision an account for clinic operations. An initial secure password must be set."
      >
        <form onSubmit={handleCreateUser} className="space-y-4 pt-2">
          {createError && (
            <Alert variant="destructive" title="Validation Error">
              {createError}
            </Alert>
          )}

          <div className="space-y-1">
            <Input
              label="Full Name"
              id="new_name"
              placeholder="e.g. Sarah Jenkins"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              disabled={isCreating}
            />
          </div>

          <div className="space-y-1">
            <Input
              label="Staff Email"
              id="new_email"
              type="email"
              placeholder="s.jenkins@physioone.com"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              required
              disabled={isCreating}
            />
          </div>

          <div className="space-y-1">
            <Input
              label="Initial Password (min 8 chars)"
              id="new_password"
              type="password"
              placeholder="••••••••••••"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              disabled={isCreating}
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700">
              Assigned Role
            </label>
            <select
              value={selectedRoleId}
              onChange={(e) => setSelectedRoleId(e.target.value)}
              className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
              disabled={isCreating}
            >
              {roles.map((r) => {
                // If current user is Admin, they cannot create an Owner account (privilege escalation prevention)
                const isOwnerRole = r.name === 'Owner';
                const disabled = currentRole === 'Admin' && isOwnerRole;

                return (
                  <option key={r.id} value={r.id} disabled={disabled}>
                    {r.name} {disabled ? '(Requires Owner role)' : `— ${r.description || ''}`}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsCreateOpen(false)}
              disabled={isCreating}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              className="bg-teal-600 hover:bg-teal-700"
              isLoading={isCreating}
              disabled={isCreating}
            >
              Create Staff Account
            </Button>
          </div>
        </form>
      </Dialog>

      {/* Action Confirmation Modal */}
      <Dialog
        isOpen={confirmModal.isOpen}
        onClose={() => setConfirmModal({ isOpen: false, type: 'deactivate', user: null })}
        title={
          confirmModal.type === 'deactivate'
            ? 'Confirm Account Deactivation'
            : confirmModal.type === 'activate'
            ? 'Confirm Account Reactivation'
            : 'Revoke User Login Sessions'
        }
        description={
          confirmModal.type === 'deactivate'
            ? `Are you sure you want to deactivate ${confirmModal.user?.full_name}? They will immediately lose access and all active sessions will be terminated.`
            : confirmModal.type === 'activate'
            ? `Reactivate account access for ${confirmModal.user?.full_name}?`
            : `Force terminate all active login sessions for ${confirmModal.user?.full_name}? The user must sign in again.`
        }
      >
        <div className="flex justify-end gap-2 pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => setConfirmModal({ isOpen: false, type: 'deactivate', user: null })}
            disabled={isActionLoading}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant={confirmModal.type === 'deactivate' ? 'destructive' : 'primary'}
            onClick={handleExecuteAction}
            isLoading={isActionLoading}
            disabled={isActionLoading}
          >
            {confirmModal.type === 'deactivate'
              ? 'Deactivate User'
              : confirmModal.type === 'activate'
              ? 'Reactivate User'
              : 'Revoke All Sessions'}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
