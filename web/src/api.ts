import { useQuery } from '@tanstack/react-query';

export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'The server could not complete this request.' }));
    throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail));
  }
  return response.json();
}

export function useApi<T = any>(path: string, interval = 0) {
  return useQuery<T>({ queryKey: [path], queryFn: () => api<T>(path), refetchInterval: interval || false });
}
