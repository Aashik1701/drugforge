import { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { funnelService } from '../services/api';
import { deriveView, parseStartError, pollInterval } from '../utils/funnelState';

/**
 * The funnel run lives on the SERVER (a `funnel` Job in the backend JobStore).
 * The frontend only needs a POINTER so it can reattach after a reload or a
 * tab reopen. That pointer is a single run_id in localStorage:
 *
 *   - localStorage survives both a tab close AND a hard refresh (sessionStorage
 *     would not survive a new tab; a URL param would not survive a plain
 *     bookmark-less reopen and would clutter the /app/funnel route).
 *   - only ONE funnel run can be active at a time (the backend 503s a second
 *     POST /start), so one scalar is enough -- no list, no per-tab state.
 *   - on mount we GET /api/funnel/status/{id}: running/queued -> reattach and
 *     poll; terminal -> show the finished run (still useful on return); 404 ->
 *     the pointer is stale, clear it and show setup.
 */
const RUN_KEY = 'drugforge.funnel.activeRunId';

const readPointer = () => {
  try {
    return localStorage.getItem(RUN_KEY) || null;
  } catch {
    return null;
  }
};
const writePointer = (id) => {
  try {
    if (id) localStorage.setItem(RUN_KEY, id);
    else localStorage.removeItem(RUN_KEY);
  } catch {
    /* private mode / disabled storage: resumability degrades, the app still works */
  }
};

export function useFunnelSets() {
  return useQuery({
    queryKey: ['funnel-sets'],
    queryFn: async () => (await funnelService.listSets()).data,
    staleTime: 5 * 60_000,
  });
}

export function useFunnelFrontier(setId) {
  return useQuery({
    queryKey: ['funnel-frontier', setId],
    enabled: !!setId,
    queryFn: async () => {
      try {
        return (await funnelService.getFrontier(setId)).data; // { set_id, rows }
      } catch (err) {
        if (err?.response?.status === 404) return { set_id: setId, rows: null };
        throw err;
      }
    },
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

export function useFunnel() {
  const qc = useQueryClient();
  const [runId, setRunId] = useState(readPointer);

  const setPointer = useCallback((id) => {
    writePointer(id);
    setRunId(id);
  }, []);

  // --- live status of the active run ---
  const statusQuery = useQuery({
    queryKey: ['funnel-status', runId],
    enabled: !!runId,
    queryFn: async () => {
      try {
        return (await funnelService.getStatus(runId)).data;
      } catch (err) {
        // surface 404 with a stable shape so deriveView can act on it
        if (err?.response?.status === 404) {
          const e = new Error('run not found');
          e.status = 404;
          throw e;
        }
        throw err;
      }
    },
    refetchInterval: (query) => pollInterval(query.state.data),
    refetchIntervalInBackground: false, // hidden tab -> stop polling entirely
    refetchOnWindowFocus: true, // returning to the tab -> immediate refetch + resume
    retry: (count, err) => (err?.status === 404 ? false : count < 3),
    gcTime: 60 * 60_000,
  });

  // a stale pointer: clear it once
  useEffect(() => {
    if (statusQuery.error?.status === 404 && runId) setPointer(null);
  }, [statusQuery.error, runId, setPointer]);

  const statusData = statusQuery.data;
  const isComplete = statusData?.status === 'completed';

  // --- the full RunRecord, only once the run is complete ---
  const resultQuery = useQuery({
    queryKey: ['funnel-result', runId],
    enabled: !!runId && isComplete,
    queryFn: async () => (await funnelService.getResult(runId)).data,
    staleTime: Infinity,
  });

  // --- start ---
  const startMutation = useMutation({
    mutationFn: async (body) => (await funnelService.start(body)).data,
    onSuccess: (data) => {
      setPointer(data.run_id);
      qc.setQueryData(['funnel-status', data.run_id], {
        run_id: data.run_id,
        status: 'queued',
        stage: 'queued',
        candidate_set_id: data.candidate_set_id,
        target: data.target,
        budget_n: data.budget_n,
        policy_id: data.policy_id,
        candidates_in: data.candidates_in,
        stage_survivors: [],
        prescreen_selected: [],
        docks_submitted: 0,
        docks_total: data.budget_n * 4,
        docks_completed: 0,
        docks_failed: 0,
        partial_results: [],
      });
    },
  });

  // --- cancel ---
  const cancelMutation = useMutation({
    mutationFn: async () => (await funnelService.cancel(runId)).data,
    onSuccess: () => statusQuery.refetch(),
  });

  const startError = startMutation.error ? parseStartError(startMutation.error) : null;

  // if a start failed because a run is already active but we HAVE a pointer,
  // treat it as a reattach rather than an error
  const reattachedAfterConflict =
    startError?.kind === 'already-active' && !!runId;

  const view = deriveView({
    runId,
    starting: startMutation.isPending,
    statusData,
    statusError: statusQuery.error,
    statusFetching: statusQuery.isFetching && !statusData,
  });

  const start = useCallback((body) => {
    startMutation.reset();
    return startMutation.mutateAsync(body).catch(() => {}); // errors surfaced via startError
  }, [startMutation]);

  const cancel = useCallback(() => cancelMutation.mutateAsync().catch(() => {}), [cancelMutation]);

  const clear = useCallback(() => {
    setPointer(null);
    startMutation.reset();
    cancelMutation.reset();
  }, [setPointer, startMutation, cancelMutation]);

  return {
    runId,
    view: reattachedAfterConflict ? 'running' : view.view,
    viewMeta: view,
    status: statusData,
    statusError: statusQuery.error,
    isStatusLoading: statusQuery.isLoading,
    result: resultQuery.data,
    isResultLoading: resultQuery.isLoading,
    resultError: resultQuery.error,
    start,
    isStarting: startMutation.isPending,
    startError: reattachedAfterConflict ? null : startError,
    cancel,
    isCancelling: cancelMutation.isPending,
    clear,
  };
}

export default useFunnel;
