import React from 'react';
import { useAuth } from 'react-oidc-context';
import { LogIn } from 'lucide-react';
import { AUTH_DISABLED } from './config';

export const RequireAuth = ({ children }: { children: React.ReactNode }) => {
    const auth = useAuth();

    if (AUTH_DISABLED) {
        return <>{children}</>;
    }

    if (auth.isLoading) {
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

                    <button
                        onClick={() => auth.signinRedirect()}
                        className="flex items-center justify-center gap-2 w-full px-4 py-3 bg-teal-600 text-white rounded-md hover:bg-teal-700 transition-colors font-medium"
                    >
                        <LogIn size={20} />
                        <span>Sign In with SSO</span>
                    </button>
                </div>
            </div>
        );
    }

    return <>{children}</>;
};
