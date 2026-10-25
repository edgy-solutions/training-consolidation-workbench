import React from 'react';
import { useAuth } from 'react-oidc-context';
import { LoginAction } from './LoginAction';
import { useLoginPending } from './useLogin';
import { AUTH_DISABLED } from './config';

export const RequireAuth = ({ children }: { children: React.ReactNode }) => {
    const auth = useAuth();
    const pending = useLoginPending();

    if (AUTH_DISABLED) {
        return <>{children}</>;
    }

    if (auth.isLoading && !pending) {
        return (
            <div className="h-screen flex items-center justify-center bg-slate-50">
                <div className="text-slate-500">Loading authentication...</div>
            </div>
        );
    }

    if (!auth.isAuthenticated) {
        return (
            <div className="h-screen flex flex-col items-center justify-center bg-slate-50">
                <div className="bg-white p-8 rounded-lg shadow-lg max-w-md w-full text-center">
                    <h1 className="text-2xl font-bold text-slate-800 mb-2">Welcome to Workbench</h1>
                    <p className="text-slate-600 mb-6">Please sign in to access the training consolidation tools.</p>

                    <LoginAction variant="card" />
                </div>
            </div>
        );
    }

    return <>{children}</>;
};
