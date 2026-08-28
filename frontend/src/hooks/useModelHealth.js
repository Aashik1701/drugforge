import { useQuery } from '@tanstack/react-query';
import { healthService } from '../services/api';

/**
 * Backend health + model registry status, via TanStack Query.
 *
 * This is the reference pattern for future server-state hooks (agent run
 * status polling, tool call results, etc.) — see docs/architecture/OVERVIEW.md.
 * Existing hooks (useDocking, useMolecule) are untouched; this only replaces
 * AppDashboard's own ad-hoc fetch/useState/useEffect.
 */
export function useModelHealth() {
  return useQuery({
    queryKey: ['model-health'],
    queryFn: async () => {
      const [healthRes, modelsRes] = await Promise.all([
        healthService.check(),
        healthService.listModels(),
      ]);
      return { health: healthRes.data, models: modelsRes.data };
    },
    staleTime: 30_000,
    retry: 1,
  });
}

export default useModelHealth;
