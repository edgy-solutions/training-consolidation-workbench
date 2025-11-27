import { create } from 'zustand';
import { api } from './api';
import type { TargetDraftNode } from './api';

interface AppState {
    discipline: string;
    projectId: string | null;
    structure: TargetDraftNode[];
    activeNodeId: string | null; // The node currently being edited/viewed in Right Pane
    activeSlideId: string | null; // The source slide currently being inspected
    
    // Actions
    setDiscipline: (d: string) => void;
    setProjectId: (id: string | null) => void;
    setActiveNodeId: (id: string | null) => void;
    setActiveSlideId: (id: string | null) => void;
    fetchStructure: () => Promise<void>;
    createProjectIfNeeded: () => Promise<void>;
    addNode: (parentId: string, title: string) => Promise<void>;
    mapSlideToNode: (nodeId: string, slideId: string) => Promise<void>;
}

export const useAppStore = create<AppState>((set, get) => ({
    discipline: 'Mechanical',
    projectId: null,
    structure: [],
    activeNodeId: null,
    activeSlideId: null,

    setDiscipline: (d) => set({ discipline: d, projectId: null, structure: [] }),
    setProjectId: (id) => set({ projectId: id }),
    setActiveNodeId: (id) => set({ activeNodeId: id }),
    setActiveSlideId: (id) => set({ activeSlideId: id }),

    fetchStructure: async () => {
        const { projectId } = get();
        if (!projectId) return;
        try {
            const nodes = await api.getDraftStructure(projectId);
            set({ structure: nodes });
        } catch (e) {
            console.error("Failed to fetch structure", e);
        }
    },

    createProjectIfNeeded: async () => {
        const { projectId, discipline } = get();
        if (projectId) return;

        try {
            const p = await api.createDraftProject(`Unified ${discipline} Standard`);
            set({ projectId: p.id });
            
            // Create initial default node
            await api.addDraftNode(p.id, "Module 1: Fundamentals");
            get().fetchStructure();
        } catch (e) {
            console.error("Failed to create project", e);
        }
    },

    addNode: async (parentId, title) => {
        try {
            await api.addDraftNode(parentId, title);
            get().fetchStructure();
        } catch (e) {
            console.error("Failed to add node", e);
        }
    },

    mapSlideToNode: async (nodeId, slideId) => {
        try {
            await api.mapSlideToNode(nodeId, [slideId]);
            get().fetchStructure(); // Refresh to see the new link
        } catch (e) {
            console.error("Failed to map slide", e);
        }
    }
}));
