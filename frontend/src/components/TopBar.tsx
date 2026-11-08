import React, { useEffect, useState } from 'react';
import { Settings, Code, Activity, Globe, Cpu, User, Layers, Tag, ClipboardCheck } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import clsx from 'clsx';
import { LoginButton } from './LoginButton';
import { LogoutButton } from './LogoutButton';
import { useAuth } from 'react-oidc-context';
import { api } from '../api';
import { DeckTemplateSettings } from './DeckTemplateSettings';
import { AlignmentReview } from './AlignmentReview';

interface TopBarProps {
    discipline: string;
    setDiscipline: (d: string) => void;
}

const SHORT_LABELS: Record<string, string> = {
    Mechanical: 'ME',
    Electrical: 'EE',
    Software: 'SWE',
    Systems: 'SysE',
};

const ICONS: Record<string, LucideIcon> = {
    Mechanical: Settings,
    Electrical: Activity, // Using Activity for waves/signals
    Software: Code,
    Systems: Globe, // Globe for big picture? Or Cpu?
};

export const TopBar: React.FC<TopBarProps> = ({ discipline, setDiscipline }) => {
    const auth = useAuth();
    const [settingsOpen, setSettingsOpen] = useState(false);
    // The gear shows only when the api has the settings screen on (WB_DECK_TEMPLATE_UI); a failed ask leaves it hidden.
    const [settingsEnabled, setSettingsEnabled] = useState(false);
    // The Review entry shows only when the flag is on and the decider grants this user; any failed ask leaves it hidden.
    const [reviewShown, setReviewShown] = useState(false);
    const [reviewOpen, setReviewOpen] = useState(false);
    // Off (WB_STORE_WRITES) means the panel opens read-only; unknown counts as off.
    const [reviewWrites, setReviewWrites] = useState(false);
    // const userDisplay = auth.user?.profile.preferred_username || auth.user?.profile.email || "Guest";

    // The buttons come from the disciplines the courses actually carry (/source/filters domains).
    // '' is "All": the tree request then sends no discipline, so courses without one show too.
    const [domains, setDomains] = useState<string[] | null>(null);

    useEffect(() => {
        api.getFilterOptions()
            .then(f => setDomains(f.domains))
            .catch(err => console.error("Failed to load disciplines", err));
    }, []);

    useEffect(() => {
        api.getDeckTemplateEnabled()
            .then(setSettingsEnabled)
            .catch(err => console.error("Failed to load the deck template setting", err));
    }, []);

    useEffect(() => {
        api.getReviewAccess()
            .then(a => {
                setReviewShown(a.enabled && a.can_review);
                setReviewWrites(a.writes_enabled === true);
            })
            .catch(err => console.error("Failed to load review access", err));
    }, []);

    // A persisted choice that no course carries any more would hide every course.
    useEffect(() => {
        if (domains && discipline && !domains.includes(discipline)) setDiscipline('');
    }, [domains, discipline, setDiscipline]);

    const disciplines = [
        { id: '', label: 'All', title: 'All disciplines', icon: Layers },
        ...(domains ?? []).map(d => ({ id: d, label: SHORT_LABELS[d] ?? d, title: d, icon: ICONS[d] ?? Tag })),
    ];

    return (
        <div className="h-14 bg-brand-dark text-white flex items-center justify-between px-4 shadow-md">
            <div className="flex items-center gap-3">
                <div className="bg-brand-teal p-1.5 rounded-lg">
                    <Cpu size={20} className="text-white" />
                </div>
                <div>
                    <h1 className="font-bold text-sm leading-tight">Training Consolidation Workbench</h1>
                    <p className="text-xs text-slate-400">Project: Global Standardization</p>
                </div>
            </div>

            {/* As many buttons as the courses have disciplines: scroll rather than crowd the bar. */}
            <div className="flex bg-slate-800 rounded-lg p-1 mx-4 min-w-0 overflow-x-auto">
                <span className="px-3 py-1 text-xs text-slate-400 font-semibold self-center">DISCIPLINE:</span>
                {disciplines.map(d => (
                    <button
                        key={d.id}
                        title={d.title}
                        onClick={() => setDiscipline(d.id)}
                        className={clsx(
                            "flex items-center gap-2 px-3 py-1 rounded-md text-sm transition-all shrink-0 whitespace-nowrap",
                            discipline === d.id
                                ? "bg-brand-teal text-white shadow-sm font-medium"
                                : "text-slate-400 hover:text-slate-200"
                        )}
                    >
                        <d.icon size={14} />
                        {d.label}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-4 text-slate-400">
                {auth.user && (
                    <div className="flex items-center gap-3 px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 hover:border-slate-600 transition-colors shadow-sm">
                        <div className="bg-brand-teal p-1 rounded-full text-white shadow-sm">
                            <User size={14} strokeWidth={2.5} />
                        </div>
                        <span className="text-sm text-white font-medium pr-1 tracking-wide">
                            {auth.user.profile.preferred_username || auth.user.profile.name || auth.user.profile.email?.split('@')[0] || "User"}
                        </span>
                    </div>
                )}
                <LoginButton />
                <LogoutButton />
                {reviewShown && (
                    <button
                        type="button"
                        title="Review alignment proposals"
                        onClick={() => setReviewOpen(true)}
                        className="flex items-center gap-1.5 text-sm hover:text-white"
                    >
                        <ClipboardCheck size={18} />
                        Review
                    </button>
                )}
                {reviewOpen && <AlignmentReview writesEnabled={reviewWrites} onClose={() => setReviewOpen(false)} />}
                {settingsEnabled && (
                    <button
                        type="button"
                        aria-label="Deck template settings"
                        title="Deck template settings"
                        onClick={() => setSettingsOpen(true)}
                        className="hover:text-white"
                    >
                        <Settings size={18} />
                    </button>
                )}
                {settingsOpen && <DeckTemplateSettings onClose={() => setSettingsOpen(false)} />}
            </div>
        </div>
    );
};
