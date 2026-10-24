// VITE_NO_AUTH=true runs the workbench without Keycloak (local dev, fixture mode).
export const AUTH_DISABLED = import.meta.env.VITE_NO_AUTH === 'true';
