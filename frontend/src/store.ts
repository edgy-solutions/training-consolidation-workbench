import { create } from 'zustand';
import { api } from './api';
import type { TargetDraftNode } from './api';

interface AppState {
    discipline: string;
    projectId: string | null;
    structure: TargetDraftNode[];
    activeNodeId: string | null; // The node currently being edited/viewed in Right Pane
    activeSlideId: string | null; // The source slide currently being inspected
    newlyAddedNodeId: string | null; // Track the most recently added node for auto-focus

    // Actions
    setDiscipline: (d: string) => void;
    setProjectId: (id: string | null) => void;
    setActiveNodeId: (id: string | null) => void;
    setActiveSlideId: (id: string | null) => void;
    setNewlyAddedNodeId: (id: string | null) => void;
    fetchStructure: () => Promise<void>;
    createProjectIfNeeded: () => Promise<void>;
    addNode: (parentId: string, title: string) => Promise<void>;
    mapSlideToNode: (nodeId: string, slideIds: string | string[]) => Promise<void>;
    updateNodeContent: (nodeId: string, markdown: string) => void;
    // Heatmap State
    heatmapMode: boolean;
    searchQuery: string;
    heatmapData: Record<string, { score: number, type: string }>;
    setHeatmapMode: (mode: boolean) => void;
    setSearchQuery: (query: string) => void;
    setHeatmapData: (data: Record<string, { score: number, type: string }>) => void;
    // Staging State
    stagingMode: boolean;
    setStagingMode: (mode: boolean) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
    discipline: 'Mechanical',
    projectId: null,
    structure: [],
    activeNodeId: null,
    activeSlideId: null,
    newlyAddedNodeId: null,

    // Heatmap State
    heatmapMode: false,
    searchQuery: '',
    heatmapData: {},

    // Staging State
    stagingMode: false,

    setDiscipline: (d) => set({ discipline: d, projectId: null, structure: [] }),
    setProjectId: (id) => set({ projectId: id }),
    setActiveNodeId: (id) => set({ activeNodeId: id }),
    setActiveSlideId: (id) => set({ activeSlideId: id }),
    setNewlyAddedNodeId: (id) => set({ newlyAddedNodeId: id }),

    setHeatmapMode: (mode) => set({ heatmapMode: mode }),
    setSearchQuery: (query) => set({ searchQuery: query }),
    setHeatmapData: (data) => set({ heatmapData: data }),
    setStagingMode: (mode) => set({ stagingMode: mode }),

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
            const newNode = await api.addDraftNode(parentId, title);
            set({ newlyAddedNodeId: newNode.id });
            get().fetchStructure();
        } catch (e) {
            console.error("Failed to add node", e);
        }
    },

    mapSlideToNode: async (nodeId, slideIds) => {
        try {
            // If slideIds is a string (legacy call), wrap it. If array, use as is.
            const ids = Array.isArray(slideIds) ? slideIds : [slideIds];
            await api.mapSlideToNode(nodeId, ids);
            get().fetchStructure(); // Refresh to see the new link
        } catch (e) {
            console.error("Failed to map slide", e);
        }
    },

    updateNodeContent: (nodeId, markdown) => {
        // Update the node's content locally without refetching from backend
        set((state) => ({
            structure: state.structure.map(node =>
                node.id === nodeId ? { ...node, content_markdown: markdown } : node
            )
        }));
    }
}));
