import { LogIn, RefreshCw } from 'lucide-react';
import { useLogin } from './useLogin';

// Sign-in button for the card (full width, with the detail line) and the TopBar
// (compact, detail as tooltip). Both render the same useLogin() state.
export const LoginAction = ({ variant }: { variant: 'card' | 'topbar' }) => {
    const login = useLogin();
    const card = variant === 'card';
    const ready = login.state === 'ready';
    const size = card ? 20 : 18;
    const tone = ready || login.state === 'opening'
        ? 'bg-teal-600 text-white hover:bg-teal-700'
        : 'bg-slate-200 text-slate-500';
    const layout = card
        ? 'flex items-center justify-center gap-2 w-full px-4 py-3 rounded-md font-medium'
        : 'flex items-center gap-2 px-4 py-2 rounded';
    const label = ready && card ? 'Sign In with SSO' : login.label;

    return (
        <div className={card ? 'space-y-3' : undefined}>
            <button
                onClick={login.start}
                disabled={!ready}
                title={!card && login.detail ? login.detail : undefined}
                className={`${layout} ${tone} transition-colors disabled:cursor-not-allowed`}
            >
                <LogIn size={size} />
                <span>{label}</span>
            </button>
            {card && login.detail && <p className="text-sm text-slate-500 break-words">{login.detail}</p>}
            {login.canRetry && (
                <button
                    onClick={login.start}
                    className={`flex items-center justify-center gap-2 text-teal-700 hover:text-teal-800 ${card ? 'w-full text-sm' : 'px-2 py-2 text-sm'}`}
                >
                    <RefreshCw size={14} />
                    <span>Retry</span>
                </button>
            )}
        </div>
    );
};
