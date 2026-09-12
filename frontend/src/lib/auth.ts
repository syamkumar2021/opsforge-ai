const TOKEN_KEY = "opsforge_token";
const EXP_KEY = "opsforge_token_exp";

function decodeJwtExp(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  const exp = decodeJwtExp(token);
  if (exp) localStorage.setItem(EXP_KEY, String(exp));
  else localStorage.removeItem(EXP_KEY);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return null;

  const expRaw = localStorage.getItem(EXP_KEY);
  if (expRaw) {
    const exp = Number(expRaw);
    if (Number.isFinite(exp) && Date.now() >= exp) {
      clearToken();
      return null;
    }
  }
  return token;
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXP_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}