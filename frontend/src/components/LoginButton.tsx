import { useAuth } from 'react-oidc-context';
import { AUTH_DISABLED } from '../auth/config';
import { LoginAction } from '../auth/LoginAction';

export const LoginButton = () => {
    const auth = useAuth();

    if (AUTH_DISABLED || auth.isAuthenticated) {
        return null;
    }

    return <LoginAction variant="topbar" />;
};
