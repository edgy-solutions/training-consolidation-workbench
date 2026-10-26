import { runtimeEnv } from '../runtimeConfig';

// VITE_NO_AUTH=true runs the workbench without Keycloak (local dev, fixture mode).
export const AUTH_DISABLED = runtimeEnv('VITE_NO_AUTH') === 'true';

// Single source of truth for the Keycloak realm. No fallbacks: an install without
// these set has no login, and the UI says so instead of pointing at a guess.
export const OIDC_AUTHORITY = (runtimeEnv('VITE_KEYCLOAK_REALM_URL') || '').trim();
export const OIDC_CLIENT_ID = (runtimeEnv('VITE_KEYCLOAK_CLIENT_ID') || '').trim();
export const LOGIN_CONFIGURED = Boolean(OIDC_AUTHORITY && OIDC_CLIENT_ID);
