// import { getToken, clearToken, saveToken } from "@/lib/auth";
// import type { AgentExecution, HumanDecisionRequest, TokenResponse, UserResponse } from "@/types/api";


// export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// async function request<T>(
//   path: string,
//   options: RequestInit = {},
//   auth = true
// ): Promise<T> {
//   const headers = new Headers(options.headers || {});

//   if (auth) {
//     const token = getToken();
//     if (token) headers.set("Authorization", `Bearer ${token}`);
//   }

//   const res = await fetch(`${API_BASE}${path}`, {
//     ...options,
//     headers,
//   });

//   if (res.status === 401) {
//     clearToken();
//     if (typeof window !== "undefined") window.location.href = "/login";
//     throw new Error("Unauthorized");
//   }

//   if (!res.ok) {
//     let detail = "Request failed";
//     try {
//       const data = await res.json();
//       detail = data.detail ? JSON.stringify(data.detail) : detail;
//     } catch {
//       // ignore
//     }
//     throw new Error(detail);
//   }

//   if (res.status === 204) return undefined as T;
//   return res.json() as Promise<T>;
// }

// export async function login(email: string, password: string): Promise<TokenResponse> {
//   const body = new URLSearchParams();
//   body.set("username", email);
//   body.set("password", password);

//   const data = await request<TokenResponse>(
//     "/api/v1/auth/token",
//     {
//       method: "POST",
//       headers: { "Content-Type": "application/x-www-form-urlencoded" },
//       body,
//     },
//     false
//   );

//   saveToken(data.access_token);
//   return data;
// }

// export async function getMe(): Promise<UserResponse> {
//   return request<UserResponse>("/api/v1/me");
// }

// export { API_BASE };



// import type { AgentExecution, HumanDecisionRequest, TokenResponse, UserResponse } from "@/types/api";

// // ... keep existing login/getMe/request code ...

// export async function listExecutions(params?: {
//   status?: string;
//   human_decision?: string;
//   limit?: number;
// }): Promise<AgentExecution[]> {
//   const q = new URLSearchParams();
//   if (params?.status) q.set("status", params.status);
//   if (params?.human_decision) q.set("human_decision", params.human_decision);
//   if (params?.limit) q.set("limit", String(params.limit));
//   const qs = q.toString();
//   return request<AgentExecution[]>(`/api/v1/executions${qs ? `?${qs}` : ""}`);
// }

// export async function getExecution(threadId: string): Promise<AgentExecution> {
//   return request<AgentExecution>(`/api/v1/executions/${threadId}`);
// }

// export async function decideExecution(
//   threadId: string,
//   payload: HumanDecisionRequest
// ): Promise<AgentExecution> {
//   return request<AgentExecution>(`/api/v1/executions/${threadId}/approve`, {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify(payload),
//   });
// }


// export type SimulateEventRequest = {
//   order_number: string;
//   exception_type: string;
//   severity: string;
//   description: string;
// };

// export type ErpOrder = {
//   id?: string;
//   order_number: string;
//   customer_id?: string;
//   customer_email?: string;
//   status?: string;
//   total_amount?: number;
//   currency?: string;
//   vendor_id?: string;
//   tracking_number?: string | null;
//   shipping_address?: Record<string, unknown>;
//   items?: Array<Record<string, unknown>>;
//   notes?: string | null;
//   created_at?: string;
//   updated_at?: string;
// };

// export async function simulateEvent(payload: SimulateEventRequest): Promise<AgentExecution> {
//   return request<AgentExecution>("/api/v1/events/simulate", {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify(payload),
//   });
// }

// export async function listErpOrders(params?: {
//   order_number?: string;
//   status?: string;
//   limit?: number;
// }): Promise<ErpOrder[]> {
//   const q = new URLSearchParams();
//   if (params?.order_number) q.set("order_number", params.order_number);
//   if (params?.status) q.set("status", params.status);
//   if (params?.limit) q.set("limit", String(params.limit ?? 50));
//   const qs = q.toString();
//   return request<ErpOrder[]>(`/api/v1/erp/orders${qs ? `?${qs}` : ""}`);
// }

// export async function feedErpOrders(orders: ErpOrder[]): Promise<any> {
//   return request<any>("/api/v1/erp/orders", {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({ orders }),
//   });
// }



import { clearToken, getToken, saveToken } from "@/lib/auth";
import type {
  AgentExecution,
  HumanDecisionRequest,
  TokenResponse,
  UserResponse,
} from "@/types/api";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth = true
): Promise<T> {
  const headers = new Headers(options.headers || {});

  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  if (options.body && !headers.has("Content-Type")) {
    if (!(options.body instanceof URLSearchParams)) {
      headers.set("Content-Type", "application/json");
    }
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail !== undefined) {
        detail =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail);
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);

  const data = await request<TokenResponse>(
    "/api/v1/auth/token",
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    },
    false
  );

  saveToken(data.access_token);
  return data;
}

export async function getMe(): Promise<UserResponse> {
  return request<UserResponse>("/api/v1/me");
}

export async function listExecutions(params?: {
  status?: string;
  human_decision?: string;
  limit?: number;
}): Promise<AgentExecution[]> {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.human_decision) q.set("human_decision", params.human_decision);
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return request<AgentExecution[]>(
    `/api/v1/executions${qs ? `?${qs}` : ""}`
  );
}

export async function getExecution(threadId: string): Promise<AgentExecution> {
  return request<AgentExecution>(`/api/v1/executions/${threadId}`);
}

export async function decideExecution(
  threadId: string,
  payload: HumanDecisionRequest
): Promise<AgentExecution> {
  return request<AgentExecution>(`/api/v1/executions/${threadId}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type SimulateEventRequest = {
  order_number: string;
  exception_type: string;
  severity: string;
  description: string;
};

export type ErpOrder = {
  id?: string;
  order_number: string;
  customer_id?: string;
  customer_email?: string;
  status?: string;
  total_amount?: number;
  currency?: string;
  vendor_id?: string;
  tracking_number?: string | null;
  shipping_address?: Record<string, unknown>;
  items?: Array<Record<string, unknown>>;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
};

export async function simulateEvent(
  payload: SimulateEventRequest
): Promise<AgentExecution> {
  return request<AgentExecution>("/api/v1/events/simulate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listErpOrders(params?: {
  order_number?: string;
  status?: string;
  limit?: number;
}): Promise<ErpOrder[]> {
  const q = new URLSearchParams();
  if (params?.order_number) q.set("order_number", params.order_number);
  if (params?.status) q.set("status", params.status);
  if (params?.limit) q.set("limit", String(params.limit ?? 50));
  const qs = q.toString();
  return request<ErpOrder[]>(`/api/v1/erp/orders${qs ? `?${qs}` : ""}`);
}

export async function feedErpOrders(
  orders: ErpOrder[]
): Promise<{ created?: number; skipped?: unknown[]; [key: string]: unknown }> {
  return request("/api/v1/erp/orders", {
    method: "POST",
    body: JSON.stringify({ orders }),
  });
}