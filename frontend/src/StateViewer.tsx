import { useEffect, useState } from 'react';
import type { AgentState, DiffResult } from './types';
import { useApi } from './api';
import { AlertCircle, Bot, Code, Database, Info, MessageSquare, Play } from 'lucide-react';

interface Props {
  runId: string;
  stepNumber: number;
  prevStepNumber?: number;
}

export function StateViewer({ runId, stepNumber, prevStepNumber }: Props) {
  const { getStepState, getDiff } = useApi();
  const [state, setState] = useState<AgentState | null>(null);
  const [diff, setDiff] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'messages' | 'tools' | 'variables' | 'diff'>('messages');

  useEffect(() => {
    let mounted = true;
    
    const fetchState = async () => {
      setLoading(true);
      try {
        const s = await getStepState(runId, stepNumber);
        if (mounted) setState(s);

        if (prevStepNumber) {
          const d = await getDiff(runId, prevStepNumber, stepNumber);
          if (mounted) setDiff(d);
        } else {
          if (mounted) setDiff(null);
        }
      } catch (err) {
        console.error("Failed to load state", err);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchState();
    return () => { mounted = false; };
  }, [runId, stepNumber, prevStepNumber]);

  if (loading) {
    return (
      <div className="empty-state">
        <Database className="spinner" size={32} />
        <p style={{ marginTop: '1rem' }}>Loading state snapshot...</p>
      </div>
    );
  }

  if (!state) return <div className="empty-state">Failed to load state.</div>;

  return (
    <div className="flex-col h-full">
      <div className="tab-list">
        <button 
          className={`tab-btn flex items-center gap-2 ${activeTab === 'messages' ? 'active' : ''}`}
          onClick={() => setActiveTab('messages')}
        >
          <MessageSquare size={16} /> Messages ({state.messages.length})
        </button>
        <button 
          className={`tab-btn flex items-center gap-2 ${activeTab === 'tools' ? 'active' : ''}`}
          onClick={() => setActiveTab('tools')}
        >
          <Code size={16} /> Tool Calls ({state.tool_calls.length})
        </button>
        <button 
          className={`tab-btn flex items-center gap-2 ${activeTab === 'variables' ? 'active' : ''}`}
          onClick={() => setActiveTab('variables')}
        >
          <Database size={16} /> Variables
        </button>
        {prevStepNumber && (
          <button 
            className={`tab-btn flex items-center gap-2 ${activeTab === 'diff' ? 'active' : ''}`}
            onClick={() => setActiveTab('diff')}
          >
            <Bot size={16} /> State Changes
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto" style={{ padding: '1.5rem' }}>
        
        {/* Error Banner */}
        {state.error && (
          <div className="glass-panel" style={{ 
            borderColor: 'var(--status-error)', 
            backgroundColor: 'var(--status-error-bg)',
            padding: '1rem',
            marginBottom: '1.5rem',
            display: 'flex', gap: '1rem', alignItems: 'flex-start'
          }}>
            <AlertCircle color="var(--status-error)" style={{ marginTop: '0.2rem' }} />
            <div>
              <h3 style={{ color: 'var(--status-error)', marginBottom: '0.5rem' }}>{state.error.error_type}</h3>
              <p className="text-sm">{state.error.message}</p>
              <pre style={{ marginTop: '1rem', background: 'rgba(0,0,0,0.2)', border: 'none' }}>
                {state.error.traceback}
              </pre>
            </div>
          </div>
        )}

        {/* Tab Contents */}
        {activeTab === 'messages' && (
          <div className="flex-col gap-4">
            {state.messages.map((msg, i) => (
              <div key={i} className={`message-bubble ${msg.role}`}>
                <div className="message-header">
                  {msg.role === 'user' ? 'User' : msg.role === 'system' ? 'System' : 'Assistant'}
                </div>
                <div>{msg.content || <em>[Empty content]</em>}</div>
              </div>
            ))}
            {state.messages.length === 0 && <div className="text-gray text-center mt-8">No messages in history.</div>}
          </div>
        )}

        {activeTab === 'tools' && (
          <div className="flex-col gap-4">
            {state.tool_calls.map((tool, i) => (
              <div key={i} className="glass-panel" style={{ padding: '1.5rem' }}>
                <h3 className="flex items-center gap-2" style={{ marginBottom: '1rem', color: 'var(--accent-base)' }}>
                  <Play size={16} /> {tool.tool_name}
                </h3>
                
                <div className="property-grid" style={{ marginBottom: '1rem' }}>
                  <span className="property-label">Status</span>
                  <span className="property-value">
                    <span className={`badge ${tool.status === 'error' ? 'badge-error' : tool.status === 'completed' ? 'badge-success' : 'badge-running'}`}>
                      {tool.status || 'unknown'}
                    </span>
                  </span>
                </div>

                <div className="property-label" style={{ marginBottom: '0.5rem' }}>Input</div>
                <pre>{typeof tool.tool_input === 'string' ? tool.tool_input : JSON.stringify(tool.tool_input, null, 2)}</pre>
                
                {tool.tool_output && (
                  <>
                    <div className="property-label" style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>Output</div>
                    <pre>{typeof tool.tool_output === 'string' ? tool.tool_output : JSON.stringify(tool.tool_output, null, 2)}</pre>
                  </>
                )}
              </div>
            ))}
            {state.tool_calls.length === 0 && <div className="text-gray text-center mt-8">No tools invoked yet.</div>}
          </div>
        )}

        {activeTab === 'variables' && (
          <div className="glass-panel" style={{ padding: '1.5rem' }}>
            <h3 className="flex items-center gap-2" style={{ marginBottom: '1rem' }}>
              <Info size={16} /> State Variables
            </h3>
            {Object.keys(state.variables).length > 0 ? (
              <pre>{JSON.stringify(state.variables, null, 2)}</pre>
            ) : (
              <div className="text-gray">No variables recorded.</div>
            )}

            <h3 className="flex items-center gap-2" style={{ marginTop: '2rem', marginBottom: '1rem' }}>
              <Info size={16} /> Metadata
            </h3>
            <pre>{JSON.stringify(state.metadata, null, 2)}</pre>
          </div>
        )}

        {activeTab === 'diff' && diff && (
          <div className="diff-container glass-panel overflow-hidden">
            <div className="diff-header text-gray">
              <div>State at Step {diff.step1}</div>
              <div>State at Step {diff.step2}</div>
            </div>
            <div className="diff-panels">
              {/* Simple diff visualization - ideally we'd use a dedicated diff library, 
                  but we'll show added/changed variables side-by-side for now */}
              <div className="diff-panel old">
                <div style={{color: 'var(--text-secondary)'}}>// Variables Before</div>
                {Object.entries(diff.changed_variables).map(([k, v]) => (
                  <div key={k} className="line-removed">
                    - {k}: {JSON.stringify(v.old)}
                  </div>
                ))}
              </div>
              <div className="diff-panel new">
                <div style={{color: 'var(--text-secondary)'}}>// Variables After</div>
                {Object.entries(diff.changed_variables).map(([k, v]) => (
                  <div key={k} className="line-added">
                    + {k}: {JSON.stringify(v.new)}
                  </div>
                ))}
                
                <div style={{color: 'var(--text-secondary)', marginTop: '2rem'}}>// New Messages ({diff.new_messages.length})</div>
                {diff.new_messages.map((m, i) => (
                  <div key={i} className="line-added">+ [{m.role}] {String(m.content).substring(0,50)}...</div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
