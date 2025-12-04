import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface ConceptNode {
    name: string;
    domain: string;
    salience?: number;
}

export interface SourceSlide {
    id: string;
    s3_url: string;
    text_preview: string;
    concepts: ConceptNode[];
}

export interface TargetDraftNode {
    id: string;
    title: string;
    parent_id?: string;
    source_refs: string[];
    status: string;
    content_markdown?: string;
    // Suggestion fields
    is_suggestion?: boolean;
    is_placeholder?: boolean; // Flag for "NO_SOURCE_DATA" sections
    is_unassigned?: boolean; // Flag for "Unassigned / For Review" section
    section_type?: string; // Template section type (introduction, mandatory_safety, technical, mandatory_assessment)
    suggested_source_ids?: string[];
    rationale?: string;
    order?: number;
}

export interface CourseNode {
    id: string;
    name: string;
    type: 'BusinessUnit' | 'Course';
    engineering_discipline?: string;
    children?: CourseNode[];
    has_children?: boolean;
}

export interface CourseSection {
    id: string;
    title: string;
    level?: number;
    concepts: string[];
}

export const api = {
    getSourceTree: async (discipline?: string) => {
        const params = discipline ? { engineering_discipline: discipline } : {};
        const res = await axios.get<CourseNode[]>(`${API_URL}/source/tree`, { params });
        return res.data;
    },
    getCourseSlides: async (courseId: string) => {
        const res = await axios.get<{ id: string, number: number, text: string }[]>(`${API_URL}/source/course/${courseId}/slides`);
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
    triggerRender: async (projectId: string, format: string = "pptx") => {
        const res = await axios.post(`${API_URL}/render/trigger`, { project_id: projectId, format });
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
