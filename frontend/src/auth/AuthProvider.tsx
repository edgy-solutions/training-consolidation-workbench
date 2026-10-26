import React from 'react';
import { AuthProvider as OidcProvider, AuthContext } from 'react-oidc-context';
import type { AuthContextProps } from 'react-oidc-context';
import { LOGIN_CONFIGURED, OIDC_AUTHORITY, OIDC_CLIENT_ID } from './config';

const oidcConfig = {
    authority: OIDC_AUTHORITY,
    client_id: OIDC_CLIENT_ID,
    redirect_uri: window.location.origin,
    onSigninCallback: () => {
        // Remove the code and state from the URL after successful login
        window.history.replaceState({}, document.title, window.location.pathname);
    }
};

// OidcProvider cannot take an empty authority, so an unconfigured install gets a
// signed-out context instead. useAuth() keeps working for every consumer.
const signedOut = { isAuthenticated: false, isLoading: false } as unknown as AuthContextProps;

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
    if (!LOGIN_CONFIGURED) {
        return <AuthContext.Provider value={signedOut}>{children}</AuthContext.Provider>;
    }
    return <OidcProvider {...oidcConfig}>{children}</OidcProvider>;
};
