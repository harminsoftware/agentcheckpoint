import { useState, useEffect } from 'react';
import type { RunInfo, StepInfo, AgentState, DiffResult } from './types';

const API_BASE = '/api';

export function useApi() {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/runs`);
      if (!res.ok) throw new Error('Failed to fetch runs');
      const data = await res.json();
      setRuns(data.runs || []);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getRun = async (runId: string) => {
    const res = await fetch(`${API_BASE}/runs/${runId}`);
    if (!res.ok) throw new Error('Failed to fetch run');
    return await res.json() as { run: RunInfo; steps: StepInfo[]; total_steps: number };
  };

  const getStepState = async (runId: string, step: number) => {
    const res = await fetch(`${API_BASE}/runs/${runId}/steps/${step}`);
    if (!res.ok) throw new Error('Failed to fetch step state');
    const data = await res.json();
    return data.state as AgentState;
  };

  const getDiff = async (runId: string, step1: number, step2: number) => {
    const res = await fetch(`${API_BASE}/runs/${runId}/diff/${step1}/${step2}`);
    if (!res.ok) throw new Error('Failed to fetch diff');
    const data = await res.json();
    return data.diff as DiffResult;
  };

  const resumeRun = async (runId: string, step?: number) => {
    const url = step 
      ? `${API_BASE}/runs/${runId}/resume?step=${step}` 
      : `${API_BASE}/runs/${runId}/resume`;
    
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to resume run');
    return await res.json();
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  return {
    runs,
    loading,
    error,
    refreshRuns: fetchRuns,
    getRun,
    getStepState,
    getDiff,
    resumeRun
  };
}
