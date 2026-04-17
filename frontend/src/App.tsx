import { useState } from 'react';
import type { RunInfo, StepInfo } from './types';
import { useApi } from './api';
import { StateViewer } from './StateViewer';
import { PlayCircle, Clock, Server, CheckCircle2, XCircle, RotateCcw } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

export default function App() {
  const { runs, loading, getRun, resumeRun } = useApi();
  const [selectedRun, setSelectedRun] = useState<RunInfo | null>(null);
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [selectedStep, setSelectedStep] = useState<number | null>(null);
  const [prevStep, setPrevStep] = useState<number | null>(null);
  const [toast, setToast] = useState<{msg: string, type: 'success'|'error'} | null>(null);

  const handleSelectRun = async (run: RunInfo) => {
    setSelectedRun(run);
    try {
      const data = await getRun(run.run_id);
      setSteps(data.steps);
      // Auto-select latest step
      if (data.steps.length > 0) {
        const latest = data.steps[data.steps.length - 1].step_number;
        const prev = data.steps.length > 1 ? data.steps[data.steps.length - 2].step_number : null;
        setSelectedStep(latest);
        setPrevStep(prev);
      } else {
        setSelectedStep(null);
        setPrevStep(null);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectStep = (index: number) => {
    setSelectedStep(steps[index].step_number);
    setPrevStep(index > 0 ? steps[index - 1].step_number : null);
  };

  const handleResume = async () => {
    if (!selectedRun) return;
    try {
      await resumeRun(selectedRun.run_id, selectedStep || undefined);
      setToast({ msg: `Successfully triggered resume for ${selectedRun.run_id}`, type: 'success' });
      // Refresh run to see new pending state
      handleSelectRun(selectedRun);
    } catch (e: any) {
      setToast({ msg: e.message || 'Failed to resume', type: 'error' });
    }
    setTimeout(() => setToast(null), 3000);
  };

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-header">
          <h1 className="flex items-center gap-2" style={{ color: 'var(--accent-base)' }}>
            <RotateCcw size={24} />
            AgentCheckpoint
          </h1>
          <p className="text-sm text-gray" style={{ marginTop: '0.25rem' }}>
            Transparent Crash Recovery & Replay
          </p>
        </div>
        
        <div className="sidebar-content">
          <h3 className="text-gray" style={{ marginBottom: '1rem', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Recent Runs
          </h3>
          
          {loading && runs.length === 0 ? (
            <div className="flex justify-center p-4"><Server size={24} className="spinner text-gray" /></div>
          ) : (
            <div className="flex-col">
              {runs.map(run => (
                <div 
                  key={run.run_id} 
                  className={`run-item ${selectedRun?.run_id === run.run_id ? 'active' : ''}`}
                  onClick={() => handleSelectRun(run)}
                >
                  <div className="flex justify-between items-center" style={{ marginBottom: '0.5rem' }}>
                    <span style={{ fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                      {run.run_id.substring(0,8)}...
                    </span>
                    <span className={`badge ${run.status === 'failed' ? 'badge-error' : run.status === 'completed' ? 'badge-success' : 'badge-running'}`}>
                      {run.status}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs text-gray">
                    <span className="flex items-center gap-1"><Server size={12} /> {run.framework}</span>
                    <span className="flex items-center gap-1"><Clock size={12} /> {formatDistanceToNow(new Date(run.updated_at))} ago</span>
                  </div>
                </div>
              ))}
              {runs.length === 0 && <div className="text-sm text-gray text-center">No runs found.</div>}
            </div>
          )}
        </div>
      </div>

      <div className="main-content">
        {!selectedRun ? (
          <div className="empty-state">
            <PlayCircle size={48} style={{ opacity: 0.2, marginBottom: '1rem' }} />
            <h2>Select a run to replay</h2>
            <p className="text-sm">View states, steps, and resume crashed agents.</p>
          </div>
        ) : (
          <>
            {/* Timeline Header */}
            <div className="timeline">
              {steps.map((step, idx) => (
                <div key={step.step_number} className="flex items-center">
                  <div 
                    title={`Step ${step.step_number} (${formatDistanceToNow(new Date(step.timestamp))} ago)`}
                    className={`timeline-node ${selectedStep === step.step_number ? 'active' : ''} ${step.has_error ? 'error' : ''}`}
                    onClick={() => handleSelectStep(idx)}
                  >
                    {step.step_number}
                  </div>
                  {idx < steps.length - 1 && (
                    <div className={`timeline-edge ${selectedStep && step.step_number < selectedStep ? 'active' : ''}`} />
                  )}
                </div>
              ))}
              {steps.length === 0 && <div className="text-sm text-gray p-4">No steps available.</div>}
              
              <div className="flex-1" />
              <button className="btn btn-primary" onClick={handleResume}>
                <PlayCircle size={16} /> Resume from Step {selectedStep}
              </button>
            </div>

            {/* Main Inspector Area */}
            {selectedStep ? (
              <StateViewer 
                runId={selectedRun.run_id} 
                stepNumber={selectedStep} 
                prevStepNumber={prevStep || undefined} 
              />
            ) : (
              <div className="empty-state text-sm">Select a step in the timeline.</div>
            )}
          </>
        )}
      </div>

      {toast && (
        <div className="toast" style={{ borderColor: toast.type === 'error' ? 'var(--status-error)' : 'var(--status-success)' }}>
          {toast.type === 'error' ? <XCircle color="var(--status-error)" /> : <CheckCircle2 color="var(--status-success)" />}
          <span>{toast.msg}</span>
        </div>
      )}
    </>
  );
}
