export type RunInfo = {
  run_id: string;
  created_at: string;
  updated_at: string;
  total_steps: number;
  status: 'running' | 'completed' | 'failed' | 'unknown';
  framework: string;
  model: string;
};

export type StepInfo = {
  step_number: number;
  timestamp: string;
  checksum: string;
  size_bytes: number;
  has_error?: boolean;
};

export type AgentState = {
  run_id: string;
  step_number: number;
  timestamp: string;
  agent_input?: any;
  messages: Array<{ role: string; content: string; [key: string]: any }>;
  tool_calls: Array<{ tool_name: string; tool_input: any; tool_output?: any; status?: string }>;
  variables: Record<string, any>;
  metadata: Record<string, any>;
  error?: {
    error_type: string;
    message: string;
    traceback: string;
    step_number: number;
  };
};

export type DiffResult = {
  step1: number;
  step2: number;
  new_messages: AgentState['messages'];
  new_tool_calls: AgentState['tool_calls'];
  changed_variables: Record<string, { old: any; new: any }>;
  metadata_diff: Record<string, { old: any; new: any }>;
};
