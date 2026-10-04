import React, { useState } from 'react';
import {
  Compass,
  Filter,
  RotateCcw,
  AlertTriangle,
  ChevronRight,
  Info,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';

export interface ScoreBreakdown {
  distance_score: number;
  availability_score: number;
  rating_score: number;
  reliability_score: number;
  workload_score: number;
  acceptance_score: number;
  total_score: number;
}

export interface CandidateMechanicData {
  mechanic_id: string;
  user_id: string;
  full_name: string;
  business_name?: string;
  experience_years: number;
  average_rating: number;
  geodesic_distance_km: number;
  service_radius_km: number;
  road_distance_km?: number;
  estimated_arrival_minutes?: number;
  active_workload_count: number;
  score: number;
  score_breakdown: ScoreBreakdown;
  eligibility_notes?: string[];
}

export interface MatchingSessionItem {
  session_id: string;
  booking_id: string;
  status: string;
  candidate_count: number;
  current_attempt: number;
  max_attempts: number;
  selected_mechanic_id?: string;
  candidates: CandidateMechanicData[];
  failure_reason?: string;
  started_at: string;
  completed_at?: string;
}

export const MatchingDashboardPage: React.FC = () => {
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [selectedSession, setSelectedSession] = useState<MatchingSessionItem | null>(null);

  const {
    data: sessions = [],
    isLoading,
    error,
    refetch,
  } = useQuery<MatchingSessionItem[]>({
    queryKey: ['admin-matching-sessions', statusFilter],
    queryFn: async () => {
      const url =
        statusFilter === 'all'
          ? '/matching/admin/sessions'
          : `/matching/admin/sessions?status_filter=${statusFilter}`;
      return await api.get<MatchingSessionItem[]>(url);
    },
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'matched':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300';
      case 'offer_pending':
        return 'bg-amber-100 text-amber-800 border-amber-300 animate-pulse';
      case 'searching':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      case 'exhausted':
      case 'failed':
        return 'bg-rose-100 text-rose-800 border-rose-300';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-300';
    }
  };

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Top Bar */}
      <div className="bg-white border-b border-slate-200/80 sticky top-16 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
                <span>Administration</span>
                <span className="text-slate-300">/</span>
                <span className="text-indigo-600">Operations</span>
                <span className="text-slate-300">/</span>
                <span>Intelligent Matching</span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                <div className="p-2 bg-indigo-100/70 text-indigo-700 rounded-lg">
                  <Compass className="w-6 h-6" />
                </div>
                <span>Intelligent Matching & Dispatch Operations</span>
              </h1>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 shadow-sm transition"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Refresh Sessions</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* Info Banner */}
        <div className="bg-gradient-to-r from-indigo-50 to-blue-50 border border-indigo-200/70 rounded-2xl p-4 sm:p-5 flex items-start gap-3.5 text-xs text-indigo-950">
          <Info className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="font-bold text-indigo-900 text-sm block">
              Deterministic Explainable Matching Model
            </span>
            <p className="text-indigo-800 leading-relaxed">
              Mechanics are discovered via PostGIS geodesic proximity and ranked using a multi-factor
              weighted heuristic: Proximity (30%), Bayesian Smoothed Rating (20%), Availability (15%),
              Reliability (15%), Workload Balancing (10%), and Acceptance Rate (10%). No opaque ML models are used.
            </p>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center justify-between gap-4 bg-white p-3 sm:px-4 rounded-xl border border-slate-200 shadow-sm text-xs">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <span className="font-semibold text-slate-700">Filter Status:</span>
            <select
              aria-label="Filter status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="all">All Sessions</option>
              <option value="offer_pending">Offer Pending</option>
              <option value="matched">Matched</option>
              <option value="searching">Searching</option>
              <option value="exhausted">Exhausted / No Match</option>
            </select>
          </div>

          <span className="text-slate-500 font-medium">
            Showing <strong className="text-slate-900">{sessions.length}</strong> matching sessions
          </span>
        </div>

        {/* Sessions List */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="p-12 text-center text-xs text-slate-500 flex flex-col items-center gap-2">
              <div className="w-7 h-7 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              <span>Loading matching sessions...</span>
            </div>
          ) : error ? (
            <div className="p-8 text-center text-xs text-rose-600 bg-rose-50/50">
              <AlertTriangle className="w-6 h-6 mx-auto mb-1 text-rose-500" />
              <span>Failed to load matching sessions.</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-500">
              <span>No matching sessions found matching the current filter.</span>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {sessions.map((sess) => (
                <div
                  key={sess.session_id}
                  onClick={() => setSelectedSession(sess)}
                  className="p-4 sm:px-6 hover:bg-slate-50/70 transition cursor-pointer flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-900 font-mono">
                        Booking #{sess.booking_id.slice(0, 8)}
                      </span>
                      <span
                        className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${getStatusBadge(
                          sess.status
                        )}`}
                      >
                        {sess.status.replace(/_/g, ' ')}
                      </span>
                      <span className="text-slate-300">•</span>
                      <span className="text-xs text-slate-500">
                        Attempt {sess.current_attempt} of {sess.max_attempts}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
                      <span>
                        Candidates Discovered: <strong className="text-slate-800">{sess.candidate_count}</strong>
                      </span>
                      {sess.failure_reason && (
                        <span className="text-rose-600 truncate max-w-md">
                          Reason: {sess.failure_reason}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-end sm:self-center">
                    <span className="text-xs text-slate-400">
                      {new Date(sess.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Explainability Inspection Modal */}
        {selectedSession && (
          <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white w-full max-w-3xl rounded-2xl shadow-2xl border border-slate-200 max-h-[90vh] flex flex-col overflow-hidden animate-scale-up">
              <div className="p-5 border-b border-slate-200 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-base text-slate-900">
                    Matching Session & Scoring Breakdown
                  </h3>
                  <span className="text-xs text-slate-500 font-mono">
                    Session ID: {selectedSession.session_id}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedSession(null)}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-100"
                >
                  Close
                </button>
              </div>

              <div className="p-5 overflow-y-auto space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 bg-slate-50 rounded-xl text-xs">
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Status</span>
                    <span className="font-bold capitalize">{selectedSession.status.replace(/_/g, ' ')}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Attempts</span>
                    <span className="font-bold">{selectedSession.current_attempt} / {selectedSession.max_attempts}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Candidates</span>
                    <span className="font-bold">{selectedSession.candidate_count} found</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Started</span>
                    <span className="font-bold">{new Date(selectedSession.started_at).toLocaleTimeString()}</span>
                  </div>
                </div>

                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-500 pt-2">
                  Ranked Candidates & Explainable Factors
                </h4>

                {selectedSession.candidates.length === 0 ? (
                  <div className="p-6 text-center text-xs text-slate-500 bg-slate-50 rounded-xl">
                    No scored candidates recorded for this session.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {selectedSession.candidates.map((cand, idx) => (
                      <div
                        key={cand.mechanic_id}
                        className="p-4 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition space-y-3"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-full bg-indigo-600 text-white text-[11px] font-bold flex items-center justify-center">
                              {idx + 1}
                            </span>
                            <span className="font-bold text-sm text-slate-900">{cand.full_name}</span>
                            {cand.business_name && (
                              <span className="text-xs text-slate-500 font-medium">({cand.business_name})</span>
                            )}
                          </div>
                          <div className="text-right">
                            <span className="text-xs font-extrabold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-md border border-indigo-200">
                              Score: {(cand.score * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>

                        {/* Explainable Factor Pills */}
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px] pt-1">
                          <div className="p-2 bg-slate-50 rounded-lg">
                            <span className="text-slate-500 block">Distance</span>
                            <span className="font-bold text-slate-800">{cand.geodesic_distance_km} km</span>
                            <span className="text-slate-400 text-[10px]"> ({(cand.score_breakdown.distance_score * 100).toFixed(0)}%)</span>
                          </div>
                          <div className="p-2 bg-slate-50 rounded-lg">
                            <span className="text-slate-500 block">Rating</span>
                            <span className="font-bold text-slate-800">{cand.average_rating > 0 ? cand.average_rating : 'New'} ★</span>
                            <span className="text-slate-400 text-[10px]"> ({(cand.score_breakdown.rating_score * 100).toFixed(0)}%)</span>
                          </div>
                          <div className="p-2 bg-slate-50 rounded-lg">
                            <span className="text-slate-500 block">Workload</span>
                            <span className="font-bold text-slate-800">{cand.active_workload_count} active</span>
                            <span className="text-slate-400 text-[10px]"> ({(cand.score_breakdown.workload_score * 100).toFixed(0)}%)</span>
                          </div>
                          <div className="p-2 bg-slate-50 rounded-lg">
                            <span className="text-slate-500 block">Reliability</span>
                            <span className="font-bold text-slate-800">{(cand.score_breakdown.reliability_score * 100).toFixed(0)}%</span>
                          </div>
                          <div className="p-2 bg-slate-50 rounded-lg">
                            <span className="text-slate-500 block">Road ETA</span>
                            <span className="font-bold text-slate-800">~{cand.estimated_arrival_minutes || 15} mins</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
