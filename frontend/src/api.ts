import axios from 'axios';

const API_URL = 'http://localhost:8000';

export interface ConceptNode {
    name: string;
    domain: string;
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
}

export interface CourseNode {
    id: string;
    name: string;
    type: 'BusinessUnit' | 'Course';
    engineering_discipline?: string;
    children?: CourseNode[];
    has_children?: boolean;
}

export const api = {
    getSourceTree: async (discipline?: string) => {
        const params = discipline ? { engineering_discipline: discipline } : {};
        const res = await axios.get<CourseNode[]>(`${API_URL}/source/tree`, { params });
        return res.data;
    },
    getCourseSlides: async (courseId: string) => {
        const res = await axios.get<{id: string, number: number, text: string}[]>(`${API_URL}/source/course/${courseId}/slides`);
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
        const res = await axios.get<{content: string, status: string}>(`${API_URL}/synthesis/preview/${nodeId}`);
        return res.data;
    }
};
