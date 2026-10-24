import { runtimeEnv } from '../runtimeConfig';

// VITE_NO_AUTH=true runs the workbench without Keycloak (local dev, fixture mode).
export const AUTH_DISABLED = runtimeEnv('VITE_NO_AUTH') === 'true';
