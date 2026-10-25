import axios from 'axios';
import { runtimeEnv } from './runtimeConfig';
import { LOGIN_CONFIGURED, OIDC_AUTHORITY, OIDC_CLIENT_ID } from './auth/config';

export const API_URL = runtimeEnv('VITE_API_URL') || 'http://localhost:8000';

// Fixture assets come back as backend-relative paths
export const assetSrc = (url?: string) => (url?.startsWith('/') ? `${API_URL}${url}` : url);
// The deck's own number when the API sent it; else the id's `_pN` suffix; else the id itself.
export const slideLabel = (id: string, number?: number) => `Slide ${number ?? id.match(/_p(\d+)$/)?.[1] ?? id}`;

// Same-titled courses differ by file and version: "deck.pptx · v2.0", or null when neither is known
export const courseSubtitle = (c: { filename?: string | null; version?: string | null }) =>
    [c.filename, c.version ? `v${c.version}` : null].filter(Boolean).join(' · ') || null;

// Row tooltip: the full title, then the short id (first 12 hex after "sha256:")
export const courseTooltip = (title: string, id: string) => `${title}\n${id.replace(/^sha256:/, '').slice(0, 12)}`;

export interface ConceptNode {
    name: string;
    domain: string;
    salience?: number | null; // null until ingest step d writes TEACHES salience
}

export interface SourceSlide {
    id: string;
    s3_url: string;
    text_preview: string;
    concepts: ConceptNode[];
    elements?: { type: string; text: string; metadata?: any }[]; // Structured unstructured elements
    number?: number; // Position in the deck
    course_id?: string;
    course_title?: string;
}

export interface TargetDraftNode {
    id: string;
    title: string;
    parent_id?: string;
    source_refs: string[];
    status: string;
    target_layout?: string; // Layout archetype (hero, documentary, split, etc.)
    suggested_layout?: string;
    content_markdown?: string; // Synthesized markdown content

    // Suggestion fields
    is_suggestion?: boolean;
    is_placeholder?: boolean; // Flag for "NO_SOURCE_DATA" sections
    is_unassigned?: boolean; // Flag for "Unassigned / For Review" section
    section_type?: string; // Template section type (introduction, mandatory_safety, technical, mandatory_assessment)
    suggested_source_ids?: string[];
    rationale?: string;
    order?: number;
    level?: number; // Hierarchy depth; the decks send top-level as 1, so the UI indents relative to each course's shallowest
}

export interface CourseNode {
    id: string;
    name: string;
    type: 'BusinessUnit' | 'Course';
    engineering_discipline?: string;
    filename?: string | null;
    version?: string | null;
    children?: CourseNode[];
    has_children?: boolean;
}

export interface CourseSection {
    id: string;
    title: string;
    level?: number;
    parent_id?: string | null; // HAS_SECTION parent; null for a top-level section
    slide_count?: number; // Slides under this section; missing on an older API
    concepts_inherited?: boolean; // True when concepts are the course fallback, not the section's own
    concepts: string[];
}

export interface TriggerRenderResponse {
    status: string;
    filename: string;
    job: string;
    run_id: string;
}

export interface RenderEventCallbacks {
    onStatus?: (data: { run_id: string; status: string }) => void;
    onComplete?: (data: { run_id: string; status: string; filename: string; download_url: string }) => void;
    onError?: (data: { run_id: string; status?: string; error?: string }) => void;
}

// Add interceptor to attach Bearer token
axios.interceptors.request.use(config => {
    if (!LOGIN_CONFIGURED) return config;

    const storageKey = `oidc.user:${OIDC_AUTHORITY}:${OIDC_CLIENT_ID}`;
    const oidcStorage = sessionStorage.getItem(storageKey);
    if (oidcStorage) {
        const user = JSON.parse(oidcStorage);
        if (user && user.access_token) {
            config.headers.Authorization = `Bearer ${user.access_token}`;
        } else {
            console.warn("[API] Found user storage but no access_token");
        }
    } else {
        console.warn(`[API] No OIDC storage found for key: ${storageKey}`);
        console.log("[API] Available keys:", Object.keys(sessionStorage));
    }
    return config;
}, error => {
    return Promise.reject(error);
});

export const api = {
    getSourceTree: async (discipline?: string) => {
        const params = discipline ? { engineering_discipline: discipline } : {};
        const res = await axios.get<CourseNode[]>(`${API_URL}/source/tree`, { params });
        return res.data;
    },
    getCourseSlides: async (courseId: string) => {
        const res = await axios.get<(SourceSlide & { number: number; text: string })[]>(`${API_URL}/source/course/${courseId}/slides`);
        return res.data;
    },
    getCourseSections: async (courseId: string) => {
        const res = await axios.get<CourseSection[]>(`${API_URL}/source/course/${courseId}/sections`);
        return res.data;
    },
    getSlideDetails: async (slideId: string) => {
        const res = await axios.get<SourceSlide>(`${API_URL}/source/slide/${slideId}`);
        return res.data;
    },
    createDraftProject: async (title: string) => {
        const res = await axios.post<TargetDraftNode>(`${API_URL}/draft/create`, null, { params: { title } });
        return res.data;
    },
    listUserProjects: async () => {
        const res = await axios.get<TargetDraftNode[]>(`${API_URL}/draft/list`);
        return res.data;
    },
    addDraftNode: async (parentId: string, title: string) => {
        const res = await axios.post<TargetDraftNode>(`${API_URL}/draft/node/add`, null, { params: { parent_id: parentId, title } });
        return res.data;
    },
    mapSlideToNode: async (nodeId: string, slideIds: string[]) => {
        const res = await axios.put(`${API_URL}/draft/node/map`, slideIds, { params: { node_id: nodeId } });
        return res.data;
    },
    getDraftStructure: async (projectId: string) => {
        const res = await axios.get<TargetDraftNode[]>(`${API_URL}/draft/structure/${projectId}`);
        return res.data;
    },
    triggerSynthesis: async (targetNodeId: string, tone: string) => {
        const res = await axios.post(`${API_URL}/synthesis/trigger`, { target_node_id: targetNodeId, tone_instruction: tone });
        return res.data;
    },
    getSynthesisPreview: async (nodeId: string) => {
        const res = await axios.get<{ content: string, status: string }>(`${API_URL}/synthesis/preview/${nodeId}`);
        return res.data;
    },
    searchConcepts: async (q: string) => {
        const res = await axios.get<string[]>(`${API_URL}/search/concepts`, { params: { q } });
        return res.data;
    },
    searchSourceTree: async (request: SearchRequest) => {
        const res = await axios.post<CourseNode[]>(`${API_URL}/source/search`, request);
        return res.data;
    },
    getFilterOptions: async () => {
        const res = await axios.get<{ origins: string[], domains: string[], intents: string[], types: string[] }>(`${API_URL}/source/filters`);
        return res.data;
    },
    generateProjectSkeleton: async (request: {
        title: string;
        domain: string | null;
        selected_source_ids: string[];
        master_course_id?: string | null;
        template_name?: string;
    }) => {
        const res = await axios.post(`${API_URL}/project/generate_skeleton`, request);
        return res.data;
    },
    getTemplates: async () => {
        const res = await axios.get<{ templates: Array<{ name: string; display_name: string }> }>(`${API_URL}/templates/list`);
        return res.data;
    },
    acceptSuggestedNode: async (nodeId: string) => {
        const res = await axios.post(`${API_URL}/draft/node/accept`, null, {
            params: { node_id: nodeId }
        });
        return res.data;
    },
    rejectSuggestedNode: async (nodeId: string) => {
        const res = await axios.delete(`${API_URL}/draft/node/reject`, {
            params: { node_id: nodeId }
        });
        return res.data;
    },
    triggerRender: async (projectId: string, format: string = "pptx", templateName: string = "standin"): Promise<TriggerRenderResponse> => {
        const res = await axios.post<TriggerRenderResponse>(`${API_URL}/render/trigger`, { project_id: projectId, format, template_name: templateName });
        return res.data;
    },
    listTemplates: async () => {
        const res = await axios.get<{ templates: string[] }>(`${API_URL}/render/templates`);
        return res.data;
    },
    getConceptHeatmap: async (term: string) => {
        const res = await axios.get<Record<string, { score: number, type: 'course' | 'slide' }>>(`${API_URL}/source/heatmap/${term}`);
        return res.data;
    },
    updateNodeContent: async (nodeId: string, markdown: string) => {
        const res = await axios.put(`${API_URL}/draft/node/content`, { content_markdown: markdown }, {
            params: { node_id: nodeId }
        });
        return res.data;
    },
    updateNodeTitle: async (nodeId: string, title: string) => {
        const res = await axios.put(`${API_URL}/draft/node/title`, { title }, {
            params: { node_id: nodeId }
        });
        return res.data;
    },
    updateNodeLayout: async (nodeId: string, layout: string) => {
        const res = await axios.put(`${API_URL}/draft/node/layout`, { target_layout: layout }, {
            params: { node_id: nodeId }
        });
        return res.data;
    },
    getEmbeddedImagesForSlides: async (slideIds: string[]): Promise<{ images: { filename: string; url: string; size: number; page_number?: number }[] }> => {
        const res = await axios.post(`${API_URL}/source/embedded-images-for-slides`, slideIds);
        return res.data;
    },

    /**
     * Subscribe to Server-Sent Events for render job status updates.
     * Returns an EventSource that can be closed when done.
     */
    subscribeRenderEvents: (runId: string, callbacks: RenderEventCallbacks): EventSource => {
        const eventSource = new EventSource(`${API_URL}/render/events/${runId}`);

        eventSource.addEventListener('status', (event) => {
            const data = JSON.parse((event as MessageEvent).data);
            callbacks.onStatus?.(data);
        });

        eventSource.addEventListener('complete', (event) => {
            const data = JSON.parse((event as MessageEvent).data);
            callbacks.onComplete?.(data);
            eventSource.close();
        });

        eventSource.addEventListener('error', (event) => {
            // Check if this is an SSE error event with data or a connection error
            const messageEvent = event as MessageEvent;
            if (messageEvent.data) {
                const data = JSON.parse(messageEvent.data);
                callbacks.onError?.(data);
            } else {
                callbacks.onError?.({ run_id: runId, error: 'Connection lost' });
            }
            eventSource.close();
        });

        return eventSource;
    },

    /**
     * Resolve stable minio:// URLs or expired presigned URLs to fresh presigned URLs.
     * Use this when loading content with embedded images to refresh expired URLs.
     */
    resolveImageUrls: async (urls: string[]): Promise<Record<string, string>> => {
        if (urls.length === 0) return {};
        const res = await axios.post<{ urls: Record<string, string> }>(`${API_URL}/source/resolve-image-urls`, urls);
        return res.data.urls;
    },

};

export interface SearchRequest {
    query?: string;
    filters?: {
        origin?: string;
        domain?: string;
        intent?: string;
        type?: string;
    };
}

export default api;
