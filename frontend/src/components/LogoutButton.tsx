import { useAuth } from 'react-oidc-context';
import { LogOut } from 'lucide-react';
import { AUTH_DISABLED } from '../auth/config';

export const LogoutButton = () => {
    const auth = useAuth();

    if (AUTH_DISABLED || !auth.isAuthenticated) {
        return null;
    }

    return (
        <button
            onClick={() => auth.signoutRedirect()}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition-colors"
            title={`Signed in as ${auth.user?.profile.preferred_username || auth.user?.profile.email}`}
        >
            <LogOut size={16} />
            <span>Sign Out</span>
        </button>
    );
};
