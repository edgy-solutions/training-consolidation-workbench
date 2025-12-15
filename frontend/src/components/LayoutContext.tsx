import React, { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';

// Layout archetypes matching PPTX template configurations
export type LayoutArchetype = 'documentary' | 'split' | 'grid' | 'hero' | 'content_caption' | 'table' | 'blank';

// Layout role options for each archetype
export const LAYOUT_ROLES: Record<LayoutArchetype, { value: string; label: string }[]> = {
    documentary: [
        { value: 'auto', label: 'Auto' },
        { value: 'main', label: 'Main Body' },
        { value: 'appendix', label: 'Appendix' },
    ],
    split: [
        { value: 'auto', label: 'Auto' },
        { value: 'left', label: 'Left Column' },
        { value: 'right', label: 'Right Column' },
    ],
    grid: [
        { value: 'auto', label: 'Auto' },
        { value: 'slot_1', label: 'Slot 1 (Top Left)' },
        { value: 'slot_2', label: 'Slot 2 (Top Right)' },
        { value: 'slot_3', label: 'Slot 3 (Bottom Left)' },
        { value: 'slot_4', label: 'Slot 4 (Bottom Right)' },
    ],
    hero: [
        { value: 'auto', label: 'Auto' },
        { value: 'background', label: 'Background Image' },
        { value: 'overlay', label: 'Overlay Content' },
    ],
    content_caption: [
        { value: 'auto', label: 'Auto' },
        { value: 'image', label: 'Main Image' },
        { value: 'caption', label: 'Caption Text' },
    ],
    table: [
        { value: 'auto', label: 'Auto' },
    ],
    blank: [
        { value: 'auto', label: 'Auto' },
    ],
};

interface LayoutContextType {
    currentLayout: LayoutArchetype;
    setCurrentLayout: (layout: LayoutArchetype) => void;
    getLayoutRoles: () => { value: string; label: string }[];
}

const LayoutContext = createContext<LayoutContextType | null>(null);

export const useLayout = () => {
    const context = useContext(LayoutContext);
    if (!context) {
        // Return default if used outside provider
        return {
            currentLayout: 'documentary' as LayoutArchetype,
            setCurrentLayout: () => { },
            getLayoutRoles: () => LAYOUT_ROLES.documentary,
        };
    }
    return context;
};

interface LayoutProviderProps {
    children: ReactNode;
    initialLayout?: LayoutArchetype;
}

export const LayoutProvider: React.FC<LayoutProviderProps> = ({
    children,
    initialLayout = 'documentary'
}) => {
    const [currentLayout, setCurrentLayout] = useState<LayoutArchetype>(initialLayout);

    // Sync with prop changes (when user changes layout via dropdown)
    useEffect(() => {
        setCurrentLayout(initialLayout);
    }, [initialLayout]);

    const getLayoutRoles = () => LAYOUT_ROLES[currentLayout];

    return (
        <LayoutContext.Provider value={{ currentLayout, setCurrentLayout, getLayoutRoles }}>
            {children}
        </LayoutContext.Provider>
    );
};

export default LayoutContext;
