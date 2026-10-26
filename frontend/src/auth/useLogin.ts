import { useCallback, useContext, useSyncExternalStore } from 'react';
import { AuthContext } from 'react-oidc-context';
import { LOGIN_CONFIGURED, OIDC_AUTHORITY, OIDC_CLIENT_ID } from './config';

export type LoginState = 'ready' | 'opening' | 'unavailable';

export interface LoginStatus {
    state: LoginState;
    label: string;
    // Why login is unavailable (null while ready/opening).
    detail: string | null;
    // True when a retry can help (the server was asked and failed), not a config gap.
    canRetry: boolean;
    start: () => void;
}

// Shared across every consumer (card, TopBar, RequireAuth) so they always agree.
let pending = false;
let failure: string | null = null;
const listeners = new Set<() => void>();
const setStore = (p: boolean, f: string | null) => {
    pending = p;
    failure = f;
    listeners.forEach(l => l());
};
const subscribe = (l: () => void) => {
    listeners.add(l);
    return () => { listeners.delete(l); };
};

// True while a sign-in redirect is in flight (react-oidc-context reports isLoading then).
export const useLoginPending = () => useSyncExternalStore(subscribe, () => pending);

function missingDetail(): string {
    if (!OIDC_AUTHORITY && !OIDC_CLIENT_ID) return 'This install has no Keycloak realm URL or client id.';
    if (!OIDC_AUTHORITY) return 'This install has no Keycloak realm URL.';
    return 'This install has no Keycloak client id.';
}

// Shared by the sign-in card and the TopBar button so their behaviour cannot drift.
export function useLogin(): LoginStatus {
    const auth = useContext(AuthContext);
    const opening = useLoginPending();
    const failed = useSyncExternalStore(subscribe, () => failure);

    const start = useCallback(() => {
        if (!auth || !LOGIN_CONFIGURED) return;
        setStore(true, null);
        auth.signinRedirect().catch((err: unknown) => {
            setStore(false, err instanceof Error ? err.message : String(err));
        });
    }, [auth]);

    if (!LOGIN_CONFIGURED) {
        return { state: 'unavailable', label: 'Login not configured', detail: missingDetail(), canRetry: false, start };
    }
    const message = failed ?? auth?.error?.message ?? null;
    if (message) {
        return {
            state: 'unavailable',
            label: 'Login not configured',
            detail: `The login server at ${OIDC_AUTHORITY} did not answer: ${message}`,
            canRetry: true,
            start,
        };
    }
    if (opening) return { state: 'opening', label: 'Opening login…', detail: null, canRetry: false, start };
    return { state: 'ready', label: 'Sign In', detail: null, canRetry: false, start };
}
