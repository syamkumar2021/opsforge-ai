export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type UserResponse = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at?: string;
};

export type ExecutionStatus =
  | "pending"
  | "running"
  | "waiting_human"
  | "completed"
  | "failed";

export type AgentExecution = {
  id: string;
  thread_id: string;
  status: ExecutionStatus | string;
  confidence?: number | null;
  plan?: string[] | null;
  report?: string | null;
  report_structured?: Record<string, unknown> | null;
  human_decision?: string | null;
  human_notes?: string | null;
  approved_by?: string | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  agents_executed?: string[] | null;
  notification_result?: Record<string, any> | null;
  event_payload?: Record<string, any> | null;
  research_data?: Record<string, any> | null;
  browser_evidence?: Record<string, any> | null;
  integration_result?: Record<string, any> | null;
};

export type HumanDecisionRequest = {
  decision: "approved" | "rejected" | "modified";
  notes?: string;
};