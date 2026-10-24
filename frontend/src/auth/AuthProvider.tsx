import React from 'react';
import { AuthProvider as OidcProvider } from 'react-oidc-context';
import { runtimeEnv } from '../runtimeConfig';

const oidcConfig = {
    authority: runtimeEnv('VITE_KEYCLOAK_REALM_URL') || "http://localhost:8080/realms/workbench",
    client_id: runtimeEnv('VITE_KEYCLOAK_CLIENT_ID') || "workbench-app",
    redirect_uri: window.location.origin,
    onSigninCallback: () => {
        // Remove the code and state from the URL after successful login
        window.history.replaceState({}, document.title, window.location.pathname);
    }
};

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
    return <OidcProvider {...oidcConfig}>{children}</OidcProvider>;
};
