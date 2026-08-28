import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { computeService } from '../services/api';

/** Current server-side compute policy (mode + limits) — same pattern as useModelHealth. */
export function useComputePolicy() {
  return useQuery({
    queryKey: ['compute-policy'],
    queryFn: async () => (await computeService.getPolicy()).data,
    staleTime: 10_000,
    retry: 1,
  });
}

/** Switch the active compute mode; refetches the policy on success. */
export function useSetComputeMode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (mode) => (await computeService.setMode(mode)).data,
    onSuccess: (newPolicy) => {
      queryClient.setQueryData(['compute-policy'], newPolicy);
    },
  });
}
