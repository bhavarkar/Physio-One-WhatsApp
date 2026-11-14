'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import {
  api,
  Appointment,
  AppointmentHistory,
  TimeSlot,
  AvailabilityResponse,
  AppointmentStatusType,
} from '@/lib/api-client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { Dialog } from '@/components/ui/dialog';
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from '@/components/ui/table';
import {
  Calendar,
  Clock,
  User,
  Phone,
  Search,
  Plus,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  AlertCircle,
  FileText,
  CalendarCheck,
  CalendarX,
  History,
  Lock,
} from 'lucide-react';

// Format UTC/ISO timestamp to IST (Asia/Kolkata) display
function formatISTDateTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(d);
  } catch {
    return isoString;
  }
}

function formatISTTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }).format(d);
  } catch {
    return isoString;
  }
}

function isDateSunday(dateStr: string): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr + 'T12:00:00+05:30');
  return d.getDay() === 0;
}

export default function AppointmentsPage() {
  const { user, role } = useAuth();
  const isViewer = role === 'Viewer';

  // Appointments list state
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [totalAppointments, setTotalAppointments] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [dateFilter, setDateFilter] = useState<string>('');

  // Modals state
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  // Create Appointment Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newPatientName, setNewPatientName] = useState('');
  const [newPatientPhone, setNewPatientPhone] = useState('');
  const [newPatientEmail, setNewPatientEmail] = useState('');
  const [newPractitioner, setNewPractitioner] = useState('Dr. Physio One');
  const [newServiceType, setNewServiceType] = useState('Initial Physiotherapy Assessment');
  const [newBookingDate, setNewBookingDate] = useState('');
  const [newDuration, setNewDuration] = useState(45);
  const [newNotes, setNewNotes] = useState('');
  const [selectedSlot, setSelectedSlot] = useState<TimeSlot | null>(null);
  const [availabilitySlots, setAvailabilitySlots] = useState<TimeSlot[]>([]);
  const [isAvailLoading, setIsAvailLoading] = useState(false);
  const [availError, setAvailError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Reschedule Modal
  const [isRescheduleOpen, setIsRescheduleOpen] = useState(false);
  const [rescheduleDate, setRescheduleDate] = useState('');
  const [rescheduleSlot, setRescheduleSlot] = useState<TimeSlot | null>(null);
  const [rescheduleSlots, setRescheduleSlots] = useState<TimeSlot[]>([]);
  const [isReschedAvailLoading, setIsReschedAvailLoading] = useState(false);
  const [rescheduleReason, setRescheduleReason] = useState('');
  const [rescheduleNotes, setRescheduleNotes] = useState('');
  const [isRescheduling, setIsRescheduling] = useState(false);

  // Cancel Modal
  const [isCancelOpen, setIsCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelNotes, setCancelNotes] = useState('');
  const [isCancelling, setIsCancelling] = useState(false);

  // Complete / No-Show Confirmation
  const [actionModal, setActionModal] = useState<{
    isOpen: boolean;
    type: 'complete' | 'no_show';
    appointment: Appointment | null;
  }>({ isOpen: false, type: 'complete', appointment: null });
  const [actionNotes, setActionNotes] = useState('');
  const [isActionLoading, setIsActionLoading] = useState(false);

  // Fetch appointments list
  const fetchAppointments = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await api.getAppointments({
        search: searchQuery.trim() || undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        date_from: dateFilter || undefined,
        date_to: dateFilter || undefined,
        sort_by: 'start_time',
        sort_order: 'asc',
      });
      setAppointments(res.appointments);
      setTotalAppointments(res.total);
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to load appointments.' });
    } finally {
      setIsLoading(false);
    }
  }, [searchQuery, statusFilter, dateFilter]);

  useEffect(() => {
    fetchAppointments();
  }, [fetchAppointments]);

  // Load availability when booking date changes
  const handleBookingDateChange = async (dateVal: string) => {
    setNewBookingDate(dateVal);
    setSelectedSlot(null);
    setAvailError(null);

    if (!dateVal) {
      setAvailabilitySlots([]);
      return;
    }

    if (isDateSunday(dateVal)) {
      setAvailError('Physio One is strictly closed on Sundays. Please select a Monday-Saturday slot.');
      setAvailabilitySlots([]);
      return;
    }

    try {
      setIsAvailLoading(true);
      const avail = await api.getAvailability(dateVal, newDuration, newPractitioner);
      if (!avail.is_open) {
        setAvailError(avail.message || 'Clinic is closed on this date.');
        setAvailabilitySlots([]);
      } else {
        setAvailabilitySlots(avail.slots);
      }
    } catch (err: any) {
      setAvailError(err.message || 'Failed to query availability.');
      setAvailabilitySlots([]);
    } finally {
      setIsAvailLoading(false);
    }
  };

  // Load availability when reschedule date changes
  const handleRescheduleDateChange = async (dateVal: string) => {
    setRescheduleDate(dateVal);
    setRescheduleSlot(null);

    if (!dateVal || isDateSunday(dateVal)) {
      setRescheduleSlots([]);
      return;
    }

    try {
      setIsReschedAvailLoading(true);
      const avail = await api.getAvailability(
        dateVal,
        selectedAppointment?.duration_minutes || 45,
        selectedAppointment?.practitioner_name
      );
      setRescheduleSlots(avail.is_open ? avail.slots : []);
    } catch {
      setRescheduleSlots([]);
    } finally {
      setIsReschedAvailLoading(false);
    }
  };

  // Handle Create Appointment Submission
  const handleCreateAppointment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPatientName.trim() || !newPatientPhone.trim()) {
      setFeedback({ type: 'error', message: 'Patient name and phone number are required.' });
      return;
    }
    if (!newBookingDate || !selectedSlot) {
      setFeedback({ type: 'error', message: 'Please select an available booking slot.' });
      return;
    }

    try {
      setIsCreating(true);
      await api.createAppointment({
        patient_name: newPatientName.trim(),
        patient_phone: newPatientPhone.trim(),
        patient_email: newPatientEmail.trim() || undefined,
        start_time: selectedSlot.start_time,
        duration_minutes: newDuration,
        practitioner_name: newPractitioner,
        service_type: newServiceType,
        notes: newNotes.trim() || undefined,
        booked_by: 'dashboard',
      });

      setFeedback({ type: 'success', message: 'Appointment booked successfully.' });
      setIsCreateOpen(false);
      resetCreateForm();
      fetchAppointments();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to book appointment.' });
    } finally {
      setIsCreating(false);
    }
  };

  const resetCreateForm = () => {
    setNewPatientName('');
    setNewPatientPhone('');
    setNewPatientEmail('');
    setNewBookingDate('');
    setSelectedSlot(null);
    setAvailabilitySlots([]);
    setNewNotes('');
    setAvailError(null);
  };

  // Handle Reschedule Submission
  const handleReschedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAppointment || !rescheduleSlot) {
      setFeedback({ type: 'error', message: 'Please select a new time slot.' });
      return;
    }

    try {
      setIsRescheduling(true);
      await api.rescheduleAppointment(selectedAppointment.id, {
        new_start_time: rescheduleSlot.start_time,
        reason: rescheduleReason.trim() || undefined,
        notes: rescheduleNotes.trim() || undefined,
      });

      setFeedback({ type: 'success', message: 'Appointment rescheduled successfully.' });
      setIsRescheduleOpen(false);
      setIsDetailOpen(false);
      fetchAppointments();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to reschedule appointment.' });
    } finally {
      setIsRescheduling(false);
    }
  };

  // Handle Cancel Submission
  const handleCancel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAppointment || !cancelReason.trim()) {
      setFeedback({ type: 'error', message: 'Cancellation reason is required.' });
      return;
    }

    try {
      setIsCancelling(true);
      await api.cancelAppointment(selectedAppointment.id, {
        reason: cancelReason.trim(),
        notes: cancelNotes.trim() || undefined,
      });

      setFeedback({ type: 'success', message: 'Appointment cancelled successfully.' });
      setIsCancelOpen(false);
      setIsDetailOpen(false);
      fetchAppointments();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to cancel appointment.' });
    } finally {
      setIsCancelling(false);
    }
  };

  // Handle Complete or No-Show
  const handleExecuteAction = async () => {
    if (!actionModal.appointment) return;

    try {
      setIsActionLoading(true);
      if (actionModal.type === 'complete') {
        await api.completeAppointment(actionModal.appointment.id, {
          notes: actionNotes.trim() || undefined,
        });
        setFeedback({ type: 'success', message: 'Appointment marked as completed.' });
      } else {
        await api.markAppointmentNoShow(actionModal.appointment.id, {
          notes: actionNotes.trim() || undefined,
        });
        setFeedback({ type: 'success', message: 'Appointment marked as no-show.' });
      }

      setActionModal({ isOpen: false, type: 'complete', appointment: null });
      setActionNotes('');
      setIsDetailOpen(false);
      fetchAppointments();
    } catch (err: any) {
      setFeedback({ type: 'error', message: err.message || 'Failed to update appointment.' });
    } finally {
      setIsActionLoading(false);
    }
  };

  // View full details with fresh history
  const handleViewDetails = async (appt: Appointment) => {
    try {
      const detailed = await api.getAppointmentDetails(appt.id);
      setSelectedAppointment(detailed);
      setIsDetailOpen(true);
    } catch {
      setSelectedAppointment(appt);
      setIsDetailOpen(true);
    }
  };

  // Status Badge Helper
  const getStatusBadge = (status: AppointmentStatusType) => {
    switch (status) {
      case 'confirmed':
        return <Badge variant="success">Confirmed</Badge>;
      case 'scheduled':
        return <Badge variant="secondary">Scheduled</Badge>;
      case 'completed':
        return <Badge variant="default">Completed</Badge>;
      case 'cancelled':
        return <Badge variant="destructive">Cancelled</Badge>;
      case 'no_show':
        return <Badge variant="warning">No-Show</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Clinical Appointments</h1>
          <p className="text-sm text-slate-500">
            Real-time calendar scheduling, practitioner availability, and Sunday closure policy (Asia/Kolkata).
          </p>
        </div>
        <div>
          <Button
            onClick={() => {
              resetCreateForm();
              setIsCreateOpen(true);
            }}
            disabled={isViewer}
            className="flex items-center gap-2"
          >
            {isViewer ? <Lock className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            Book Appointment
          </Button>
        </div>
      </div>

      {/* Global Sunday Invariant Alert */}
      <Alert variant="warning" title="Clinic Invariant: Sunday Closure Enforced">
        Physio One is strictly closed on Sundays. The backend availability engine authoritatively blocks and rejects
        all Sunday bookings across dashboard, API, and WhatsApp channels.
      </Alert>

      {/* Action Feedback */}
      {feedback && (
        <Alert
          variant={feedback.type === 'success' ? 'success' : 'destructive'}
          title={feedback.type === 'success' ? 'Operation Succeeded' : 'Error'}
        >
          {feedback.message}
        </Alert>
      )}

      {/* Filters Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col lg:flex-row gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search patient name, phone, or notes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>

            {/* Date Filter */}
            <div className="w-full sm:w-48">
              <Input
                type="date"
                value={dateFilter}
                onChange={(e) => setDateFilter(e.target.value)}
                placeholder="Filter by date"
              />
            </div>

            {/* Status Filter */}
            <div className="w-full sm:w-48">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full h-10 px-3 border rounded-md text-sm border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="all">All Statuses</option>
                <option value="scheduled">Scheduled</option>
                <option value="confirmed">Confirmed</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
                <option value="no_show">No-Show</option>
              </select>
            </div>

            {/* Refresh */}
            <Button
              variant="outline"
              onClick={() => {
                setSearchQuery('');
                setStatusFilter('all');
                setDateFilter('');
                fetchAppointments();
              }}
              className="flex items-center gap-1.5"
            >
              <RefreshCw className="h-4 w-4" />
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Appointments List Table */}
      <Card>
        <CardHeader className="border-b border-slate-100 pb-4">
          <CardTitle className="text-base flex items-center justify-between">
            <span>Appointments Directory</span>
            <span className="text-xs font-normal text-slate-500">{totalAppointments} total records</span>
          </CardTitle>
          <CardDescription>
            Appointments in Physio One clinic timezone (Asia/Kolkata). Click any row to inspect audit history.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-16 text-center text-sm text-slate-500 space-y-2">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto text-indigo-600" />
              <p>Loading appointments calendar...</p>
            </div>
          ) : appointments.length === 0 ? (
            <div className="py-16 text-center text-slate-500 space-y-3">
              <Calendar className="h-10 w-10 mx-auto text-slate-300" />
              <p className="font-medium text-slate-700">No appointments found</p>
              <p className="text-xs max-w-sm mx-auto text-slate-400">
                No appointments match your active filter criteria. Try adjusting your date or search parameters.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Patient</TableHead>
                  <TableHead>Date & Time (IST)</TableHead>
                  <TableHead>Practitioner & Service</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {appointments.map((appt) => (
                  <TableRow key={appt.id} className="hover:bg-slate-50/70 cursor-pointer" onClick={() => handleViewDetails(appt)}>
                    <TableCell>
                      <div className="font-medium text-slate-900">{appt.patient_name || 'Patient'}</div>
                      <div className="text-xs text-slate-500 flex items-center gap-1">
                        <Phone className="h-3 w-3" />
                        {appt.patient_phone || 'N/A'}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-slate-800">{formatISTDateTime(appt.start_time)}</div>
                      <div className="text-xs text-slate-500">
                        {formatISTTime(appt.start_time)} - {formatISTTime(appt.end_time)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm text-slate-800">{appt.service_type}</div>
                      <div className="text-xs text-slate-500">{appt.practitioner_name}</div>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">{appt.duration_minutes} mins</TableCell>
                    <TableCell>{getStatusBadge(appt.status)}</TableCell>
                    <TableCell className="text-right space-x-2" onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleViewDetails(appt)}
                      >
                        Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* ----------------- MODAL 1: Book Appointment Dialog ----------------- */}
      <Dialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Book New Clinical Appointment"
        description="Select date and an available slot. Sundays are prohibited by backend policy."
      >
        <form onSubmit={handleCreateAppointment} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Patient Full Name *</label>
              <Input
                placeholder="e.g. Ramesh Patel"
                value={newPatientName}
                onChange={(e) => setNewPatientName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Phone Number (E.164) *</label>
              <Input
                placeholder="+919876543210"
                value={newPatientPhone}
                onChange={(e) => setNewPatientPhone(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Practitioner</label>
              <Input
                value={newPractitioner}
                onChange={(e) => setNewPractitioner(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Service Type</label>
              <select
                value={newServiceType}
                onChange={(e) => setNewServiceType(e.target.value)}
                className="w-full h-10 px-3 border rounded-md text-sm border-slate-300 bg-white"
              >
                <option value="Initial Physiotherapy Assessment">Initial Assessment (45m)</option>
                <option value="Follow-up Physical Therapy">Follow-up Therapy (45m)</option>
                <option value="Post-Op Rehabilitation">Post-Op Rehab (60m)</option>
                <option value="Sports Injury Consultation">Sports Injury Consult (45m)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Booking Date (Monday - Saturday) *</label>
            <Input
              type="date"
              value={newBookingDate}
              onChange={(e) => handleBookingDateChange(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              required
            />
            {newBookingDate && isDateSunday(newBookingDate) && (
              <p className="mt-1 text-xs text-rose-600 font-medium flex items-center gap-1">
                <AlertCircle className="h-3.5 w-3.5" />
                Selected date is a Sunday. Clinic is closed.
              </p>
            )}
          </div>

          {/* Slot Picker */}
          {newBookingDate && !isDateSunday(newBookingDate) && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Available Slots (IST)</label>
              {isAvailLoading ? (
                <div className="p-4 text-center text-xs text-slate-500">Checking slot availability...</div>
              ) : availError ? (
                <Alert variant="destructive">{availError}</Alert>
              ) : availabilitySlots.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No available slots found for this date.</p>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-48 overflow-y-auto p-1 border rounded-md">
                  {availabilitySlots.map((slot, idx) => (
                    <button
                      key={idx}
                      type="button"
                      disabled={!slot.is_available}
                      onClick={() => setSelectedSlot(slot)}
                      className={`text-xs py-2 px-1 rounded text-center border transition-all ${
                        !slot.is_available
                          ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed line-through'
                          : selectedSlot === slot
                          ? 'bg-indigo-600 text-white border-indigo-600 font-medium'
                          : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-400'
                      }`}
                    >
                      {formatISTTime(slot.start_time)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Internal Notes</label>
            <textarea
              className="w-full p-2 border rounded-md text-sm border-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              rows={2}
              placeholder="Clinical or scheduling notes..."
              value={newNotes}
              onChange={(e) => setNewNotes(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isCreating || !selectedSlot || (newBookingDate ? isDateSunday(newBookingDate) : true)}
            >
              {isCreating ? 'Booking...' : 'Confirm Appointment'}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* ----------------- MODAL 2: Appointment Details & Timeline ----------------- */}
      <Dialog
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        title="Appointment Record & Audit Timeline"
        description={`ID: ${selectedAppointment?.id}`}
      >
        {selectedAppointment && (
          <div className="space-y-5">
            {/* Summary Grid */}
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-50 rounded-lg text-xs">
              <div>
                <span className="text-slate-400 block">Patient</span>
                <span className="font-semibold text-slate-800">{selectedAppointment.patient_name || 'N/A'}</span>
                <span className="text-slate-500 block">{selectedAppointment.patient_phone}</span>
              </div>
              <div>
                <span className="text-slate-400 block">Status</span>
                <div className="mt-0.5">{getStatusBadge(selectedAppointment.status)}</div>
              </div>
              <div>
                <span className="text-slate-400 block">Date & Time</span>
                <span className="font-semibold text-slate-800">
                  {formatISTDateTime(selectedAppointment.start_time)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block">Practitioner</span>
                <span className="font-semibold text-slate-800">{selectedAppointment.practitioner_name}</span>
                <span className="text-slate-500 block">{selectedAppointment.service_type}</span>
              </div>
              {selectedAppointment.cancellation_reason && (
                <div className="col-span-2 p-2 bg-rose-50 border border-rose-200 rounded text-rose-800">
                  <span className="font-semibold block">Cancellation Reason:</span>
                  {selectedAppointment.cancellation_reason}
                </div>
              )}
            </div>

            {/* Audit & Lifecycle History */}
            <div>
              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <History className="h-3.5 w-3.5 text-indigo-600" />
                Lifecycle & Reschedule History
              </h4>
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {!selectedAppointment.history_entries || selectedAppointment.history_entries.length === 0 ? (
                  <p className="text-xs text-slate-400 italic">No history records logged.</p>
                ) : (
                  selectedAppointment.history_entries.map((h) => (
                    <div key={h.id} className="p-2 border rounded-md text-xs space-y-1 bg-white">
                      <div className="flex items-center justify-between text-slate-500">
                        <span className="font-semibold text-indigo-700 uppercase">{h.action}</span>
                        <span>{formatISTDateTime(h.created_at)}</span>
                      </div>
                      {h.from_start_time && h.to_start_time && (
                        <div className="text-slate-600">
                          Rescheduled from <span className="font-medium">{formatISTDateTime(h.from_start_time)}</span> to{' '}
                          <span className="font-medium text-indigo-900">{formatISTDateTime(h.to_start_time)}</span>
                        </div>
                      )}
                      {h.reason && <div className="text-slate-600 italic">Reason: {h.reason}</div>}
                      {h.notes && <div className="text-slate-500">Notes: {h.notes}</div>}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Lifecycle Action Buttons */}
            {!isViewer && ['scheduled', 'confirmed'].includes(selectedAppointment.status) && (
              <div className="pt-3 border-t flex flex-wrap gap-2 justify-end">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setRescheduleDate('');
                    setRescheduleSlot(null);
                    setRescheduleReason('');
                    setIsRescheduleOpen(true);
                  }}
                  className="flex items-center gap-1"
                >
                  <CalendarCheck className="h-3.5 w-3.5" />
                  Reschedule
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setActionModal({ isOpen: true, type: 'complete', appointment: selectedAppointment });
                  }}
                  className="text-emerald-700 hover:bg-emerald-50"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Mark Completed
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setActionModal({ isOpen: true, type: 'no_show', appointment: selectedAppointment });
                  }}
                  className="text-amber-700 hover:bg-amber-50"
                >
                  <AlertCircle className="h-3.5 w-3.5" />
                  No-Show
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setCancelReason('');
                    setCancelNotes('');
                    setIsCancelOpen(true);
                  }}
                  className="text-rose-700 hover:bg-rose-50"
                >
                  <CalendarX className="h-3.5 w-3.5" />
                  Cancel
                </Button>
              </div>
            )}
          </div>
        )}
      </Dialog>

      {/* ----------------- MODAL 3: Reschedule Dialog ----------------- */}
      <Dialog
        isOpen={isRescheduleOpen}
        onClose={() => setIsRescheduleOpen(false)}
        title="Reschedule Appointment"
        description="Choose a new date and available slot. Sunday appointments are rejected."
      >
        <form onSubmit={handleReschedule} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">New Date (Mon - Sat) *</label>
            <Input
              type="date"
              value={rescheduleDate}
              onChange={(e) => handleRescheduleDateChange(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              required
            />
            {rescheduleDate && isDateSunday(rescheduleDate) && (
              <p className="mt-1 text-xs text-rose-600 font-medium">Physio One is strictly closed on Sundays.</p>
            )}
          </div>

          {rescheduleDate && !isDateSunday(rescheduleDate) && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Select Available Slot (IST)</label>
              {isReschedAvailLoading ? (
                <div className="p-3 text-center text-xs text-slate-500">Querying availability...</div>
              ) : rescheduleSlots.length === 0 ? (
                <p className="text-xs text-slate-400 italic">No available slots for this date.</p>
              ) : (
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-40 overflow-y-auto p-1 border rounded-md">
                  {rescheduleSlots.map((slot, idx) => (
                    <button
                      key={idx}
                      type="button"
                      disabled={!slot.is_available}
                      onClick={() => setRescheduleSlot(slot)}
                      className={`text-xs py-2 px-1 rounded text-center border transition-all ${
                        !slot.is_available
                          ? 'bg-slate-100 text-slate-400 border-slate-200 cursor-not-allowed line-through'
                          : rescheduleSlot === slot
                          ? 'bg-indigo-600 text-white border-indigo-600 font-medium'
                          : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-400'
                      }`}
                    >
                      {formatISTTime(slot.start_time)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Rescheduling Reason</label>
            <Input
              placeholder="e.g. Patient requested morning slot"
              value={rescheduleReason}
              onChange={(e) => setRescheduleReason(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button type="button" variant="outline" onClick={() => setIsRescheduleOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isRescheduling || !rescheduleSlot || (rescheduleDate ? isDateSunday(rescheduleDate) : true)}
            >
              {isRescheduling ? 'Rescheduling...' : 'Confirm Reschedule'}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* ----------------- MODAL 4: Cancel Appointment Dialog ----------------- */}
      <Dialog
        isOpen={isCancelOpen}
        onClose={() => setIsCancelOpen(false)}
        title="Cancel Appointment"
        description="Record cancellation reason. Physical appointment record will be preserved in history."
      >
        <form onSubmit={handleCancel} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Cancellation Reason *</label>
            <Input
              placeholder="e.g. Patient unwell, emergency conflict"
              value={cancelReason}
              onChange={(e) => setCancelReason(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Additional Notes</label>
            <textarea
              className="w-full p-2 border rounded-md text-sm border-slate-300 focus:outline-none"
              rows={2}
              placeholder="Optional notes regarding cancellation..."
              value={cancelNotes}
              onChange={(e) => setCancelNotes(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button type="button" variant="outline" onClick={() => setIsCancelOpen(false)}>
              Back
            </Button>
            <Button type="submit" variant="destructive" disabled={isCancelling || !cancelReason.trim()}>
              {isCancelling ? 'Cancelling...' : 'Confirm Cancellation'}
            </Button>
          </div>
        </form>
      </Dialog>

      {/* ----------------- MODAL 5: Complete / No-Show Confirmation ----------------- */}
      <Dialog
        isOpen={actionModal.isOpen}
        onClose={() => setActionModal({ isOpen: false, type: 'complete', appointment: null })}
        title={actionModal.type === 'complete' ? 'Mark Appointment Completed' : 'Mark Appointment as No-Show'}
        description="This state transition is terminal and will be permanently recorded in the audit log."
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Staff Notes</label>
            <textarea
              className="w-full p-2 border rounded-md text-sm border-slate-300 focus:outline-none"
              rows={2}
              placeholder="Clinical outcome or no-show notes..."
              value={actionNotes}
              onChange={(e) => setActionNotes(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => setActionModal({ isOpen: false, type: 'complete', appointment: null })}
            >
              Cancel
            </Button>
            <Button onClick={handleExecuteAction} disabled={isActionLoading}>
              {isActionLoading ? 'Updating...' : 'Confirm'}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
