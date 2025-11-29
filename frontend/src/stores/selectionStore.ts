import { create } from 'zustand';

interface SelectionStore {
    selectedSourceIds: Set<string>;
    toggleSelection: (id: string) => void;
    selectMultiple: (ids: string[]) => void;
    deselectMultiple: (ids: string[]) => void;
    clearSelection: () => void;
    isSelected: (id: string) => boolean;
}

export const useSelectionStore = create<SelectionStore>((set, get) => ({
    selectedSourceIds: new Set<string>(),

    toggleSelection: (id: string) => set((state) => {
        const newSet = new Set(state.selectedSourceIds);
        if (newSet.has(id)) {
            newSet.delete(id);
        } else {
            newSet.add(id);
        }
        return { selectedSourceIds: newSet };
    }),

    selectMultiple: (ids: string[]) => set((state) => {
        const newSet = new Set(state.selectedSourceIds);
        ids.forEach(id => newSet.add(id));
        return { selectedSourceIds: newSet };
    }),

    deselectMultiple: (ids: string[]) => set((state) => {
        const newSet = new Set(state.selectedSourceIds);
        ids.forEach(id => newSet.delete(id));
        return { selectedSourceIds: newSet };
    }),

    clearSelection: () => set({ selectedSourceIds: new Set<string>() }),

    isSelected: (id: string) => get().selectedSourceIds.has(id)
}));
