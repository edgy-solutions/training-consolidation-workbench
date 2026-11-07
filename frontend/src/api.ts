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

// The HTTP status and the body's `detail` of a failed request; both undefined when there was no response.
export const httpError = (e: unknown): { status?: number; detail?: unknown } =>
    axios.isAxiosError(e) ? { status: e.response?.status, detail: e.response?.data?.detail } : {};

export interface ConceptSource {
    slide_id: string;
    filename: string;
    number: number;
    in_section: boolean;
}

export interface ConceptRepeat {
    id: string;
    title: string;
    role: string;
}

export interface SectionConcept {
    concept: string;
    sources: ConceptSource[];
    repeated_in: ConceptRepeat[];
    overlap: boolean;
}

export interface SectionConcepts {
    exported: boolean;
    inherited: boolean;
    concepts: SectionConcept[];
}

export type RenderGateDetail =
    | { kind: 'unfinished'; message: string; unfinished: number; total: number; sections: { id: string; title: string }[] }
    | { kind: 'problems'; message: string; problems: string[] }
    | { kind: 'concept_overlap'; message: string; overlaps: { concept: string; sections: { id: string; title: string }[] }[] };

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

// --- Deck template settings (docs/contracts/deck-template.md section 8) ---
export interface TemplatePlaceholder {
    idx: number;
    name: string;
    type: string;
    accepts_image: boolean;
    mappable: boolean;
    left: number | null; // EMU
    top: number | null;
    width: number | null;
    height: number | null;
}

export interface TemplateLayout {
    name: string;
    index: number; // 0-based position among all layouts, masters in order; a mapping's layout_index
    name_count: number; // > 1: several layouts carry this name; the mapping disambiguates by index and warns
    placeholders: TemplatePlaceholder[];
}

export interface TemplateInspection {
    slide_width: number;
    slide_height: number;
    layouts: TemplateLayout[];
}

// field -> placeholder idx, or 'notes-page' for the notes field
export type FieldMapping = Record<string, number | string>;
export type RoleMapping = Record<string, { layout: string; layout_index?: number; placeholders: FieldMapping }>;

export interface DeckTemplateSettings {
    source: 'saved' | 'deployment' | 'standin';
    store_enabled: boolean;
    can_configure: boolean;
    filename: string | null;
    saved_by: string | null;
    saved_at: string | null;
    role_spec: Record<string, { required: string[]; optional: string[] }>;
    roles: RoleMapping;
    template: TemplateInspection;
    warnings: string[];
}

export interface GenerateJob {
    job_id: string;
    status: 'QUEUED' | 'RUNNING' | 'SUCCESS' | 'FAILURE' | 'LOST';
    step: string | null;
    elapsed?: number;
    result: { project_id: string; section_count: number; unassigned_count: number } | null;
    error: string | null;
    steps: Array<{ key: string; label: string }>;
}

export interface AlignmentProposal {
    concept_id: string;
    concept: string;
    canonical_id: string;
    canonical: string;
    members?: string[];
    confidence?: number | null;
    method?: string | null;
    evidence?: string | null;
    cos?: number | null;
    shared?: number | null;
}

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
        const res = await axios.post<GenerateJob>(`${API_URL}/project/generate_skeleton`, request);
        return res.data;
    },
    getGenerateJob: async (jobId: string) => {
        const res = await axios.get<GenerateJob>(`${API_URL}/project/generate_skeleton/${jobId}`);
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
    triggerRender: async (projectId: string, format: string = "pptx", templateName: string = "standin", renderAnywayReason?: string): Promise<TriggerRenderResponse> => {
        const res = await axios.post<TriggerRenderResponse>(`${API_URL}/render/trigger`, {
            project_id: projectId, format, template_name: templateName,
            ...(renderAnywayReason ? { render_anyway_reason: renderAnywayReason } : {}),
        });
        return res.data;
    },
    getSectionConcepts: async (projectId: string) => {
        const res = await axios.get<{ sections: Record<string, SectionConcepts> }>(`${API_URL}/draft/concepts/${projectId}`);
        return res.data.sections;
    },
    removeSectionConcept: async (nodeId: string, concept: string) => {
        const res = await axios.post<{ node_id: string; concepts: string[] }>(`${API_URL}/draft/node/concept/remove`, { node_id: nodeId, concept });
        return res.data;
    },
    listTemplates: async () => {
        const res = await axios.get<{ templates: string[] }>(`${API_URL}/render/templates`);
        return res.data;
    },
    getDeckTemplate: async () => {
        const res = await axios.get<DeckTemplateSettings>(`${API_URL}/settings/deck-template`);
        return res.data;
    },
    getReviewAccess: async () => {
        const res = await axios.get<{ enabled: boolean; can_review: boolean; writes_enabled: boolean }>(`${API_URL}/alignment/review-access`);
        return res.data;
    },
    getAlignmentProposals: async (courseId: string) => {
        const res = await axios.get<AlignmentProposal[]>(`${API_URL}/alignment/proposals`, { params: { course_id: courseId } });
        return res.data;
    },
    reviewAlignmentProposal: async (conceptId: string, canonicalId: string, decision: 'accept' | 'reject') => {
        const res = await axios.post(`${API_URL}/alignment/proposals/review`, { concept_id: conceptId, canonical_id: canonicalId, decision });
        return res.data;
    },
    getDeckTemplateEnabled: async () => {
        const res = await axios.get<{ enabled: boolean }>(`${API_URL}/settings/deck-template/enabled`);
        return res.data.enabled;
    },
    inspectDeckTemplate: async (file: File) => {
        const form = new FormData();
        form.append('file', file);
        const res = await axios.post<TemplateInspection>(`${API_URL}/settings/deck-template/inspect`, form);
        return res.data;
    },
    saveDeckTemplate: async (roles: RoleMapping, file?: File | null) => {
        const form = new FormData();
        form.append('roles', JSON.stringify(roles));
        if (file) form.append('file', file);
        const res = await axios.put<DeckTemplateSettings>(`${API_URL}/settings/deck-template`, form);
        return res.data;
    },
    resetDeckTemplate: async () => {
        const res = await axios.delete<DeckTemplateSettings>(`${API_URL}/settings/deck-template`);
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
