// Config the container injects at start: frontend/docker/40-runtime-config.sh writes
// /config.js, which index.html loads before the app. In `vite dev`, public/config.js is
// empty, so the VITE_* build env applies.
export type RuntimeKey = 'VITE_API_URL' | 'VITE_KEYCLOAK_REALM_URL' | 'VITE_KEYCLOAK_CLIENT_ID' | 'VITE_NO_AUTH';

declare global {
    interface Window {
        __RUNTIME_CONFIG__?: Partial<Record<RuntimeKey, string>>;
    }
}

export function runtimeEnv(key: RuntimeKey): string | undefined {
    return window.__RUNTIME_CONFIG__?.[key] || import.meta.env[key];
}
